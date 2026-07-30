# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/api/routes/ai.py
# Rotte del relay IA. Montate sotto /api/v1 (vedi app/main.py), quindi il
# frontend le raggiunge esattamente dove gia le cerca:
#   `${VITE_API_URL}/ai/chat`  con VITE_API_URL = https://.../api/v1
#
# ROTTE
#   POST   /ai/chat          inoltra al fornitore e RIPASSA lo stream SSE
#   POST   /ai/count-tokens  conteggio token preventivo (stesso inoltro)
#   GET    /ai/health        il relay c'e? e configurato?   (SENZA autenticazione)
#   GET    /ai/credential    per quali fornitori ho una chiave? (mai la chiave)
#   PUT    /ai/credential    registro/sostituisco la MIA chiave
#   DELETE /ai/credential    revoco la MIA chiave
#
# PERCHE /ai/health NON E AUTENTICATA: il suo unico compito e far distinguere
# al frontend «il relay non esiste su questo backend» (404) da «esiste ma non
# e configurato» da «esiste, e configurato, ed e il fornitore a rifiutare».
# Se rispondesse 401 a chi non ha ancora un token, quella distinzione si
# perderebbe proprio nel caso in cui serve. Non espone nulla di personale:
# solo interruttori di configurazione e l'elenco pubblico dei fornitori.
#
# DIVIETO: nessun `print`, nessun `logging`. Da queste rotte passano il
# portafoglio dell'utente (nel corpo) e la sua chiave. Nemmeno per debug.
# ============================================================

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.repositories.ai_credential import AiCredentialRepository
from app.schemas.ai import (
    AiCredentialListResponse,
    AiCredentialResponse,
    AiCredentialUpsertRequest,
    AiHealthResponse,
    AiRelayRequest,
)
from app.services.ai_relay import (
    MSG_CREDENTIAL_MISSING,
    MSG_CREDENTIAL_UNREADABLE,
    AiRelayProvider,
    decrypt_api_key,
    encrypt_api_key,
    encryption_is_configured,
    enforce_user_quota,
    ensure_relay_enabled,
    key_hint,
    relay_health,
    relay_to_provider,
    resolve_path,
    resolve_provider,
)
from app.utils.exceptions import AppException
from app.utils.rate_limit import limiter

router = APIRouter(prefix="/ai", tags=["AI Relay"])


class AiCredentialMissingException(AppException):
    """La chiave del fornitore non e registrata per QUESTO utente.

    412 e non 404: il frontend interpreta un 404 sul percorso del proxy come
    «il relay non esiste su questo backend» (transport.ts:378-380,
    AI_PROXY_MISSING_MESSAGE), che qui sarebbe falso e manderebbe l'utente a
    cercare un problema di deploy invece della sua chiave mancante.
    """

    def __init__(self, message: str = MSG_CREDENTIAL_MISSING):
        super().__init__(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=message,
        )


def _chiave_utente(db: Session, user: User, provider: AiRelayProvider) -> str:
    """Chiave in chiaro dell'UTENTE CORRENTE per quel fornitore.

    ★ Non esiste una chiave di riserva del server: se l'utente non ne ha
      registrata una, la richiesta si ferma qui e non parte nulla.
    """
    repository = AiCredentialRepository(db)
    credential = repository.find_by_user_and_provider(user.id, provider.id)
    if credential is None:
        raise AiCredentialMissingException()

    chiave = decrypt_api_key(credential.api_key_enc)
    if not chiave:
        # Ciphertext non piu leggibile: la chiave di cifratura del server e
        # cambiata. Va detto con parole diverse da «non l'hai mai registrata»,
        # perche la cura e la stessa ma la causa no.
        raise AiCredentialMissingException(MSG_CREDENTIAL_UNREADABLE)
    return chiave


async def _inoltra(
    data: AiRelayRequest,
    current_user: User,
    db: Session,
):
    """Corpo comune di /ai/chat e /ai/count-tokens."""
    ensure_relay_enabled()
    provider = resolve_provider(data.provider)
    path = resolve_path(provider, data.path)
    # Il tetto si applica PRIMA di leggere la chiave e prima di aprire
    # qualunque connessione: chi e oltre il limite non deve nemmeno costare
    # una query.
    enforce_user_quota(current_user.id)
    # ★ La lettura della credenziale e I/O BLOCCANTE (psycopg2) dentro una
    #   rotta `async`: eseguita sul loop bloccherebbe, per quel millisecondo,
    #   ANCHE gli stream degli altri utenti gia in corso. Va nel threadpool,
    #   come farebbe FastAPI con una dipendenza sincrona.
    chiave = await run_in_threadpool(_chiave_utente, db, current_user, provider)
    return await relay_to_provider(
        provider=provider,
        path=path,
        stream=data.stream,
        body=data.body,
        api_key=chiave,
    )


@router.post("/chat")
async def ai_chat(
    data: AiRelayRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Inoltra il turno al fornitore e ripassa la risposta SENZA bufferizzarla.

    Con `stream: true` la risposta e un `text/event-stream` consegnato pezzo
    per pezzo: e cio che fa comparire il testo parola per parola nel pannello.
    Con `stream: false` e la risposta JSON del fornitore, sempre in transito,
    mai accumulata in memoria dal backend.
    """
    return await _inoltra(data, current_user, db)


@router.post("/count-tokens")
async def ai_count_tokens(
    data: AiRelayRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Conteggio token preventivo (solo i fornitori che lo offrono).

    Il frontend lo chiama da `countTokens()` e tratta ogni fallimento come
    «non calcolabile», quindi qui non serve nessuna gentilezza in piu: lo
    stesso inoltro basta.
    """
    return await _inoltra(data, current_user, db)


@router.get("/health", response_model=AiHealthResponse)
@limiter.limit("60/minute")
def ai_health(request: Request):
    """Il relay c'e ed e configurato? Rotta pubblica, nessun dato personale.

    Se questa rotta risponde 404, il relay non e installato su questo backend:
    e esattamente il caso che il frontend gia descrive con
    AI_PROXY_MISSING_MESSAGE.
    """
    return relay_health()


def _risposta_credenziale(credential, provider_id: str) -> AiCredentialResponse:
    """Vista pubblica di una credenziale. LA CHIAVE NON C'E, e non ci sara mai."""
    if credential is None:
        return AiCredentialResponse(provider=provider_id, configured=False)
    return AiCredentialResponse(
        provider=credential.provider_id,
        configured=True,
        key_hint=credential.key_hint,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


@router.get("/credential", response_model=AiCredentialListResponse)
def ai_list_credentials(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per quali fornitori ho registrato una chiave.

    Risponde SOLO se esiste e per quale fornitore: la chiave non torna MAI
    indietro, nemmeno parzialmente (le 4 cifre di `key_hint` servono a
    riconoscerla, non a ricostruirla).
    """
    repository = AiCredentialRepository(db)
    credenziali = repository.list_by_user(current_user.id)
    return AiCredentialListResponse(
        items=[_risposta_credenziale(c, c.provider_id) for c in credenziali]
    )


@router.put("/credential", response_model=AiCredentialResponse)
def ai_put_credential(
    data: AiCredentialUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Registra o sostituisce la MIA chiave per un fornitore.

    La chiave viene cifrata (Fernet) prima di toccare il database. Se il server
    non ha una chiave di cifratura configurata, la rotta fallisce con 503 e lo
    dice: mai un salvataggio in chiaro, mai una cifratura con chiave effimera.
    """
    provider = resolve_provider(data.provider)
    # `encrypt_api_key` solleva gia 503 se la cifratura non e configurabile;
    # il controllo esplicito tiene il messaggio vicino al punto d'uso.
    if not encryption_is_configured():
        # Delega a _get_fernet, che produce il messaggio esatto (assente o non valida).
        encrypt_api_key("controllo-configurazione")

    chiara = data.api_key.get_secret_value().strip()
    repository = AiCredentialRepository(db)
    credential = repository.upsert(
        user_id=current_user.id,
        provider_id=provider.id,
        api_key_enc=encrypt_api_key(chiara),
        key_hint=key_hint(chiara),
    )
    return _risposta_credenziale(credential, provider.id)


@router.delete("/credential", response_model=AiCredentialResponse)
def ai_delete_credential(
    provider: str = Query(..., min_length=1, max_length=32, description="Identificativo del fornitore"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoca la MIA chiave per un fornitore.

    IDEMPOTENTE di proposito: se non c'era nulla da revocare risponde 200 con
    `configured: false`, non 404. Un 404 su questo percorso e ambiguo — il
    frontend lo legge come «il relay non esiste» — e per un'azione di
    azzeramento «non c'era niente» e comunque il risultato voluto.
    """
    voce = resolve_provider(provider)
    repository = AiCredentialRepository(db)
    repository.delete_by_user_and_provider(current_user.id, voce.id)
    return _risposta_credenziale(None, voce.id)
