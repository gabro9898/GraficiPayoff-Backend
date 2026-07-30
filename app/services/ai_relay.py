# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/services/ai_relay.py
# INOLTRO vero verso i fornitori di modelli, piu la custodia cifrata delle
# chiavi. Il frontend (src/services/ai/transport.ts) manda a `/ai/chat` la
# busta `{provider, path, stream, body}` col corpo NATIVO del fornitore: qui
# si aggiunge la chiave dell'utente e si ripassa la risposta.
#
# ─────────────────────── DIVIETI VINCOLANTI ───────────────────────
#  1. NON SI BUFFERIZZA. La risposta viaggia con `httpx.AsyncClient.stream`
#     e `StreamingResponse`: se si accumulasse il corpo prima di rispondere,
#     la chat smetterebbe di scrivere parola per parola. Per questo si usa
#     `aiter_raw()` e si chiede al fornitore `Accept-Encoding: identity`:
#     nessuno strato di decompressione in mezzo, byte per byte come arrivano.
#  2. NON SI REGISTRA NULLA. Nessun `print`, nessun `logging`: da qui passano
#     il prompt, il portafoglio dell'utente e la sua chiave. Nemmeno per debug.
#  3. VERSO IL FORNITORE NON ESCE NULLA DELL'APP. Gli header della richiesta
#     in ingresso (compreso il Bearer JWT dell'app) NON vengono inoltrati: si
#     costruisce da zero un set di header minimo.
#  4. OGNI UTENTE USA SOLO LA PROPRIA CHIAVE. La chiave si legge dalla riga
#     `ai_credentials` di QUELL'utente, mai da una configurazione globale.
#  5. IL PERCORSO E SU ELENCO CHIUSO. `path` arriva dal client: senza un
#     elenco di percorsi ammessi per fornitore, il relay sarebbe un proxy
#     aperto pagato con la chiave di qualcun altro.
#
# ─────────────────────── MAPPATURA DEGLI ERRORI ───────────────────────
# Il frontend interpreta i codici HTTP con messaggi gia scritti
# (transport.ts:370-393), quindi il relay NON puo ripassare i codici del
# fornitore cosi come sono:
#   - un 404 del fornitore diventerebbe «il relay non esiste» (falso) ->
#     lo si traduce in 400, dove il frontend mostra anche il dettaglio;
#   - un 401 del fornitore diventerebbe «esci e rientra nell'app» (falso) ->
#     lo si traduce in 403, che il frontend spiega gia come «chiave del
#     modello rifiutata o revocata»;
#   - 429, 529 e 5xx passano invariati: li il messaggio del frontend e giusto.
# ============================================================

import math
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
# `limits` e il motore su cui slowapi e costruito ed e gia installato come sua
# dipendenza: qui NON si aggiunge nulla al requirements. Serve perche il
# messaggio del 429 debba dire QUANTO MANCA al ripristino, e quel dato sta
# nella finestra del limitatore, non nel decoratore.
import limits
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.utils.rate_limit import limiter

# ─────────────────────────── Catalogo dei fornitori ───────────────────────────


@dataclass(frozen=True)
class AiRelayProvider:
    """Voce del catalogo lato server.

    Rispecchia src/services/ai/providerCatalog.ts: stessi identificativi,
    stessi indirizzi di base, stessi percorsi. Se una delle due tabelle cambia,
    l'altra va allineata a mano — sono due processi diversi e non c'e modo di
    condividere il file.
    """

    id: str
    label: str
    base_url: str
    # "x-api-key" (Anthropic) oppure "bearer" (dialetto compatibile OpenAI).
    auth: str
    extra_headers: dict[str, str]
    allowed_paths: frozenset[str]


# Valore dell'header `anthropic-version`: e la versione del contratto REST,
# non del modello. Identico a AI_ANTHROPIC_VERSION del frontend.
AI_ANTHROPIC_VERSION = "2023-06-01"

_OPENAI_PATHS = frozenset({"/chat/completions"})

AI_RELAY_PROVIDERS: dict[str, AiRelayProvider] = {
    "anthropic": AiRelayProvider(
        id="anthropic",
        label="Anthropic (Claude)",
        base_url="https://api.anthropic.com",
        auth="x-api-key",
        extra_headers={"anthropic-version": AI_ANTHROPIC_VERSION},
        allowed_paths=frozenset({"/v1/messages", "/v1/messages/count_tokens"}),
    ),
    "openai": AiRelayProvider(
        id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        auth="bearer",
        extra_headers={},
        allowed_paths=_OPENAI_PATHS,
    ),
    "deepseek": AiRelayProvider(
        id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        auth="bearer",
        extra_headers={},
        allowed_paths=_OPENAI_PATHS,
    ),
    "perplexity": AiRelayProvider(
        id="perplexity",
        label="Perplexity",
        base_url="https://api.perplexity.ai",
        auth="bearer",
        extra_headers={},
        allowed_paths=_OPENAI_PATHS,
    ),
    "openrouter": AiRelayProvider(
        id="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        auth="bearer",
        extra_headers={},
        allowed_paths=_OPENAI_PATHS,
    ),
    "groq": AiRelayProvider(
        id="groq",
        label="Groq",
        base_url="https://api.groq.com/openai/v1",
        auth="bearer",
        extra_headers={},
        allowed_paths=_OPENAI_PATHS,
    ),
}

# Fornitori LOCALI del catalogo del frontend: girano sul PC dell'utente e la
# chiamata parte diretta dal renderer, senza passare di qui. Se arrivano
# comunque, la risposta deve dirlo con parole precise invece che «fornitore
# sconosciuto», che manderebbe l'utente a cercare un errore inesistente.
AI_LOCAL_PROVIDER_IDS = frozenset({"ollama", "lmstudio"})


def list_relay_providers() -> list[AiRelayProvider]:
    """Fornitori inoltrabili, in ordine stabile."""
    return [AI_RELAY_PROVIDERS[key] for key in sorted(AI_RELAY_PROVIDERS)]


# ─────────────────────────── Messaggi (italiano) ───────────────────────────

MSG_RELAY_DISABLED = (
    "Il relay IA e presente ma spento su questo server (AI_RELAY_ENABLED=false). "
    "Nessuna richiesta e stata inoltrata ad alcun fornitore."
)

MSG_ENCRYPTION_MISSING = (
    "Il relay IA non e configurato: manca la chiave di cifratura del server "
    "(AI_ENCRYPTION_KEY). Senza quella le chiavi dei fornitori non possono essere "
    "custodite cifrate, quindi il server si rifiuta di salvarle o di usarle. "
    "Va impostata nella configurazione del backend."
)

MSG_ENCRYPTION_INVALID = (
    "Il relay IA non e configurato correttamente: la chiave di cifratura del server "
    "non e una chiave Fernet valida. Rigenerala e riavvia il backend."
)

MSG_LOCAL_PROVIDER = (
    "Questo fornitore gira sul tuo PC e non passa dal backend: l'applicazione deve "
    "chiamarlo direttamente. Nessuna richiesta e stata inoltrata."
)

MSG_UNKNOWN_PROVIDER = (
    "Fornitore non riconosciuto dal relay di questo backend. I fornitori ammessi sono: "
)

MSG_PATH_NOT_ALLOWED = (
    "Percorso non ammesso per questo fornitore. Il relay inoltra solo un elenco chiuso "
    "di percorsi, per non diventare un proxy verso indirizzi arbitrari."
)

MSG_CREDENTIAL_MISSING = (
    "Chiave del fornitore non registrata: apri le impostazioni dell'assistente IA e "
    "inserisci la TUA chiave per questo fornitore. Il backend usa solo la chiave del "
    "tuo profilo e non ne ha una di riserva."
)

MSG_CREDENTIAL_UNREADABLE = (
    "La chiave registrata non e piu decifrabile con la chiave di cifratura attuale del "
    "server: e stata sostituita o persa. Registra di nuovo la tua chiave del fornitore."
)

MSG_UPSTREAM_TIMEOUT = (
    "Il fornitore non ha risposto entro il tempo massimo: la richiesta e stata annullata "
    "dal backend. Riprova, oppure scegli un modello meno carico."
)

MSG_UPSTREAM_UNREACHABLE = (
    "Il fornitore non e raggiungibile dal backend: la connessione non si e aperta. "
    "Non e un problema della tua chiave."
)

MSG_UPSTREAM_NOT_FOUND = (
    "Il fornitore non conosce il percorso richiesto: tipicamente l'indirizzo di base o il "
    "nome del modello non corrispondono a quel servizio."
)

MSG_UPSTREAM_AUTH = (
    "Il fornitore ha rifiutato la chiave registrata (credenziale non valida o revocata). "
    "Registra di nuovo la tua chiave nelle impostazioni dell'assistente IA."
)

MSG_UPSTREAM_BAD_RESPONSE = "Il fornitore ha risposto in un modo che il relay non ha potuto inoltrare."


def _messaggio_salute(enabled: bool, encryption_ok: bool) -> str:
    if not enabled:
        return MSG_RELAY_DISABLED
    if not encryption_ok:
        return MSG_ENCRYPTION_MISSING
    return (
        "Relay IA attivo e configurato. Ogni utente usa la propria chiave, custodita "
        "cifrata sul server: se una chiamata fallisce, il motivo arriva dal fornitore."
    )


# ─────────────────────────── Cifratura a riposo ───────────────────────────

# Fernet DEDICATO all'assistente IA. Volutamente separato da
# app/utils/encryption.py (token dei broker): li, se la chiave manca, si ripiega
# su una chiave effimera con un warning. Qui NO — una chiave effimera
# produrrebbe righe indecifrabili al primo riavvio, cioe un guasto silenzioso
# che si scopre giorni dopo. Se la chiave manca, le rotte falliscono subito e
# lo dicono.
_fernet: Fernet | None = None
_fernet_key_used: str | None = None


def encryption_is_configured() -> bool:
    """True se il server puo cifrare/decifrare le chiavi dei fornitori."""
    key = get_settings().AI_ENCRYPTION_KEY.strip()
    if not key:
        return False
    try:
        Fernet(key.encode())
    except Exception:
        return False
    return True


def _get_fernet() -> Fernet:
    """Fernet dell'assistente IA. Solleva 503 esplicito se non configurabile."""
    global _fernet, _fernet_key_used
    key = get_settings().AI_ENCRYPTION_KEY.strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=MSG_ENCRYPTION_MISSING,
        )
    if _fernet is None or _fernet_key_used != key:
        try:
            _fernet = Fernet(key.encode())
        except Exception:
            _fernet = None
            _fernet_key_used = None
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=MSG_ENCRYPTION_INVALID,
            )
        _fernet_key_used = key
    return _fernet


def encrypt_api_key(plaintext: str) -> str:
    """Cifra la chiave del fornitore. Il chiaro non esce da questa funzione."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str | None:
    """Decifra la chiave. `None` = ciphertext non piu leggibile (chiave cambiata)."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except HTTPException:
        raise
    except (InvalidToken, ValueError, TypeError):
        return None


def key_hint(plaintext: str) -> str:
    """Ultime 4 cifre, per far riconoscere all'utente quale chiave ha registrato."""
    pulita = plaintext.strip()
    return pulita[-4:] if len(pulita) >= 4 else ""


# ─────────────────────────── Tetto di consumo per utente ───────────────────────────

_rate_item: limits.RateLimitItem | None = None
_rate_item_source: str | None = None


def _get_rate_item() -> limits.RateLimitItem | None:
    """Tetto configurato, gia interpretato. `None` se la stringa e illeggibile."""
    global _rate_item, _rate_item_source
    grezzo = get_settings().AI_RELAY_RATE_LIMIT.strip()
    if not grezzo:
        return None
    if _rate_item is None or _rate_item_source != grezzo:
        try:
            _rate_item = limits.parse(grezzo)
        except Exception:
            _rate_item = None
            _rate_item_source = None
            return None
        _rate_item_source = grezzo
    return _rate_item


def _durata_in_italiano(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'o' if seconds == 1 else 'i'}"
    minuti = seconds // 60
    resto = seconds % 60
    testa = f"{minuti} minut{'o' if minuti == 1 else 'i'}"
    if resto == 0:
        return testa
    return f"{testa} e {resto} second{'o' if resto == 1 else 'i'}"


def enforce_user_quota(user_id: str) -> None:
    """Tetto per UTENTE sul relay. Solleva 429 dicendo quanto manca al ripristino.

    Il tetto lato client e un'indicazione che si puo aggirare svuotando lo
    storage del browser: questa e la difesa vera, e vive sul server.

    Usa il limitatore gia configurato in app/utils/rate_limit.py (la stessa
    memoria degli altri limiti), ma con una chiave costruita sull'identita
    dell'utente invece che sull'IP: due utenti dietro lo stesso ufficio non
    devono consumarsi il tetto a vicenda.

    Se il limitatore stesso si rompe (memoria non disponibile) si LASCIA
    PASSARE: un guasto dell'accessorio non deve spegnere la funzione.
    """
    item = _get_rate_item()
    if item is None:
        return

    strategia = limiter.limiter
    try:
        consentito = strategia.hit(item, "ai-relay", user_id)
    except Exception:
        return
    if consentito:
        return

    mancano = 60
    try:
        stats = strategia.get_window_stats(item, "ai-relay", user_id)
        mancano = max(1, int(math.ceil(stats.reset_time - time.time())))
    except Exception:
        pass

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"Hai raggiunto il tetto di {item.amount} richieste all'assistente IA "
            f"({item}). Il conteggio riparte fra {_durata_in_italiano(mancano)}. "
            "Nessuna richiesta e stata inoltrata al fornitore e non ti e stato addebitato nulla."
        ),
        headers={"Retry-After": str(mancano)},
    )


# ─────────────────────────── Validazione della busta ───────────────────────────


def resolve_provider(provider_id: str) -> AiRelayProvider:
    """Voce di catalogo, o l'errore che spiega perche non c'e."""
    pulito = (provider_id or "").strip().lower()
    if pulito in AI_LOCAL_PROVIDER_IDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_LOCAL_PROVIDER)
    provider = AI_RELAY_PROVIDERS.get(pulito)
    if provider is None:
        ammessi = ", ".join(sorted(AI_RELAY_PROVIDERS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{MSG_UNKNOWN_PROVIDER}{ammessi}.",
        )
    return provider


def resolve_path(provider: AiRelayProvider, path: str) -> str:
    """Percorso inoltrabile, su ELENCO CHIUSO."""
    pulito = (path or "").strip()
    if pulito not in provider.allowed_paths:
        ammessi = ", ".join(sorted(provider.allowed_paths))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{MSG_PATH_NOT_ALLOWED} Per «{provider.id}» sono ammessi: {ammessi}.",
        )
    return pulito


def ensure_relay_enabled() -> None:
    if not get_settings().AI_RELAY_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=MSG_RELAY_DISABLED,
        )


# ─────────────────────────── Redazione dei segreti ───────────────────────────

# Stesse forme riconosciute dal frontend (types.ts:119-123): e la rete di
# sicurezza perche un messaggio d'errore del fornitore, ricopiato alla lettera,
# non finisca sotto gli occhi dell'utente con una chiave dentro.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:x-api-key|api[-_]?key|authorization|access[-_]?token)\s*[:=]\s*[^\s,;\"']{8,}",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:sk-ant|sk-or|sk-proj|sk|pk|gsk|xai|pplx|ollama)[-_][A-Za-z0-9_-]{12,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
)

_SECRET_PLACEHOLDER = "[credenziale-rimossa]"

# Stesso taglio del frontend (AI_ERROR_BODY_MAX_CHARS).
_MAX_DETAIL_CHARS = 400


def redact_secrets(text: str, api_key: str | None = None) -> str:
    """Toglie da un testo ogni forma riconoscibile di credenziale."""
    if not text:
        return ""
    out = text
    if api_key:
        pulita = api_key.strip()
        if len(pulita) >= 8:
            out = out.replace(pulita, _SECRET_PLACEHOLDER)
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(_SECRET_PLACEHOLDER, out)
    return out


def _dettaglio_fornitore(raw: bytes, api_key: str | None) -> str:
    """Estratto REDATTO del corpo d'errore del fornitore, tagliato corto."""
    if not raw:
        return ""
    try:
        testo = raw.decode("utf-8", errors="replace")
    except Exception:
        return ""
    testo = redact_secrets(" ".join(testo.split()), api_key)
    if not testo:
        return ""
    if len(testo) > _MAX_DETAIL_CHARS:
        return f"{testo[:_MAX_DETAIL_CHARS]}…"
    return testo


def _mappa_errore_fornitore(upstream_status: int, dettaglio: str) -> tuple[int, str]:
    """Traduce l'errore del fornitore in un codice che il frontend spiega bene.

    Vedi la nota in testa al file: il frontend ha un messaggio gia scritto per
    ogni codice, e due di quei messaggi sarebbero FALSI se ripassassimo il
    codice originale (404 = «relay assente», 401 = «rifai il login»).
    """
    coda = f" Dettaglio dal fornitore: {dettaglio}" if dettaglio else ""

    if upstream_status == 404:
        return status.HTTP_400_BAD_REQUEST, f"{MSG_UPSTREAM_NOT_FOUND}{coda}"
    if upstream_status in (401, 403):
        return status.HTTP_403_FORBIDDEN, f"{MSG_UPSTREAM_AUTH}{coda}"
    if upstream_status in (429, 529):
        return upstream_status, f"Il fornitore ha rifiutato la richiesta.{coda}"
    if upstream_status >= 500:
        return upstream_status, f"Errore interno del fornitore.{coda}"
    return upstream_status, f"Il fornitore ha rifiutato la richiesta.{coda}"


# ─────────────────────────── Inoltro ───────────────────────────


def _upstream_headers(provider: AiRelayProvider, api_key: str, stream: bool) -> dict[str, str]:
    """Header MINIMI costruiti da zero.

    ★ Non si copia NIENTE dalla richiesta in ingresso: il Bearer JWT dell'app,
      i cookie e gli header del browser non devono uscire verso un terzo.
    ★ `Accept-Encoding: identity` serve a NON BUFFERIZZARE: senza, httpx
      negozierebbe gzip e i byte andrebbero decompressi prima di poter essere
      ripassati, spezzando la consegna incrementale.
    """
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
        "Accept-Encoding": "identity",
    }
    headers.update(provider.extra_headers)
    if provider.auth == "x-api-key":
        headers["x-api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


# Header della risposta verso il client. `X-Accel-Buffering: no` impedisce a un
# reverse proxy (nginx/Render) di accumulare lo stream e riconsegnarlo tutto
# insieme: senza, la chat tornerebbe a comparire in blocco pur essendo il relay
# corretto.
_RESPONSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}


async def relay_to_provider(
    *,
    provider: AiRelayProvider,
    path: str,
    stream: bool,
    body: dict[str, Any],
    api_key: str,
) -> StreamingResponse:
    """Inoltra la richiesta e RIPASSA la risposta senza bufferizzarla.

    Sequenza:
      1. si apre lo stream verso il fornitore (`stream=True`): a questo punto
         sono arrivati solo gli header, il corpo non e stato letto;
      2. se lo stato e un errore, IL CORPO SI LEGGE (e corto) e si solleva
         HTTPException: farlo qui, prima di rispondere, e l'unico momento in
         cui si puo ancora scegliere il codice di stato;
      3. altrimenti si ritorna una `StreamingResponse` che consuma
         `aiter_raw()` pezzo per pezzo.

    ★ CANCELLAZIONE: quando il client chiude, Starlette chiude il generatore;
      il blocco `finally` esegue `aclose()` su risposta e client, e quello
      chiude davvero la connessione col fornitore. Senza quel `finally` la
      richiesta continuerebbe a essere fatturata dopo che l'utente ha premuto
      «ferma».
    """
    settings = get_settings()
    url = f"{provider.base_url}{path}"
    headers = _upstream_headers(provider, api_key, stream)

    timeout = httpx.Timeout(
        connect=15.0,
        read=settings.AI_RELAY_READ_TIMEOUT_SECONDS,
        write=30.0,
        pool=15.0,
    )
    # Il client NON usa `async with`: deve sopravvivere al ritorno della
    # funzione e vivere quanto il generatore che lo consuma. Lo chiude il
    # `finally` del generatore (o i rami d'errore qui sotto).
    client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    try:
        request = client.build_request("POST", url, json=body, headers=headers)
        upstream = await client.send(request, stream=True)
    except httpx.TimeoutException:
        await client.aclose()
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=MSG_UPSTREAM_TIMEOUT
        )
    except httpx.HTTPError:
        await client.aclose()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=MSG_UPSTREAM_UNREACHABLE
        )

    if upstream.status_code >= 400:
        try:
            grezzo = await upstream.aread()
        except Exception:
            grezzo = b""
        await upstream.aclose()
        await client.aclose()
        codice, messaggio = _mappa_errore_fornitore(
            upstream.status_code, _dettaglio_fornitore(grezzo, api_key)
        )
        raise HTTPException(status_code=codice, detail=messaggio)

    media_type = upstream.headers.get(
        "content-type", "text/event-stream" if stream else "application/json"
    )

    async def passthrough():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            # Eseguito anche quando il client si stacca a meta: e QUESTO che
            # propaga la cancellazione fino al fornitore.
            try:
                await upstream.aclose()
            finally:
                await client.aclose()

    return StreamingResponse(
        passthrough(),
        status_code=upstream.status_code,
        media_type=media_type,
        headers=dict(_RESPONSE_HEADERS),
    )


# ─────────────────────────── Salute ───────────────────────────


def relay_health() -> dict[str, Any]:
    """Fotografia della configurazione del relay. Nessun segreto, nessun conteggio."""
    settings = get_settings()
    enabled = bool(settings.AI_RELAY_ENABLED)
    encryption_ok = encryption_is_configured()
    return {
        "relay": True,
        "enabled": enabled,
        "encryption_configured": encryption_ok,
        "providers": [
            {
                "id": provider.id,
                "label": provider.label,
                "allowed_paths": sorted(provider.allowed_paths),
            }
            for provider in list_relay_providers()
        ],
        "rate_limit": settings.AI_RELAY_RATE_LIMIT,
        "message": _messaggio_salute(enabled, encryption_ok),
    }
