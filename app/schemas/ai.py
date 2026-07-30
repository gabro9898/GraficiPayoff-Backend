# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/schemas/ai.py
# Modelli Pydantic del relay IA.
#
# ★ IL CONTRATTO LO DETTA IL FRONTEND, che e gia scritto e testato:
#   src/services/ai/transport.ts — `AiProxyEnvelope`:
#       { provider: string, path: string, stream: boolean, body: unknown }
#   inviato in POST a `${VITE_API_URL}/ai/chat` (e `/ai/count-tokens`).
#   Qui non si inventa nulla: ci si adatta a quella busta.
#
# `body` e il corpo NATIVO del fornitore (dialetto Anthropic o OpenAI) e
# attraversa il backend INALTERATO: il relay non conosce i dialetti, aggiunge
# solo la chiave. Per questo e un dizionario libero e non un modello tipizzato.
#
# ATTENZIONE: `body` contiene il portafoglio dell'utente e `api_key` contiene
# un segreto. Nessuno dei due deve MAI finire in un log, in un messaggio
# d'errore o in una risposta. Per questo `api_key` e un `SecretStr`: cosi
# nemmeno un `repr()` accidentale del modello puo stamparlo.
# ============================================================

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, SecretStr, field_validator

# Lunghezza massima del percorso inoltrato: un valore piu lungo di cosi non e
# un percorso di API, e un tentativo di infilare altro.
_MAX_PATH_LEN = 200


class AiRelayRequest(BaseModel):
    """Busta del relay, identica a `AiProxyEnvelope` del frontend."""

    provider: str = Field(..., min_length=1, max_length=32)
    path: str = Field(..., min_length=1, max_length=_MAX_PATH_LEN)
    stream: bool = False
    body: dict[str, Any] = Field(default_factory=dict)

    # Campi in piu vengono ignorati: il frontend puo arricchire la busta senza
    # che il backend inizi a rispondere 422.
    model_config = {"extra": "ignore"}

    @field_validator("provider")
    @classmethod
    def _provider_pulito(cls, value: str) -> str:
        pulito = value.strip().lower()
        if not pulito:
            raise ValueError("Il fornitore non puo essere vuoto.")
        return pulito

    @field_validator("path")
    @classmethod
    def _path_relativo(cls, value: str) -> str:
        """Il percorso deve restare RELATIVO al fornitore scelto.

        Senza questo controllo la busta diventerebbe un proxy aperto: chiunque
        abbia un account potrebbe farsi inoltrare richieste verso host arbitrari
        usando la chiave di un altro. L'elenco chiuso dei percorsi ammessi sta
        in app/services/ai_relay.py; qui si scartano le forme palesemente
        ostili prima ancora di guardare il catalogo.
        """
        pulito = value.strip()
        if not pulito.startswith("/"):
            raise ValueError("Il percorso deve iniziare con «/».")
        if pulito.startswith("//"):
            raise ValueError("Il percorso non puo iniziare con «//».")
        if ".." in pulito or "\\" in pulito:
            raise ValueError("Il percorso contiene caratteri non ammessi.")
        if "://" in pulito or "@" in pulito:
            raise ValueError("Il percorso non puo contenere un indirizzo completo.")
        return pulito


class AiCredentialUpsertRequest(BaseModel):
    """Registrazione (o sostituzione) della chiave PROPRIA dell'utente."""

    provider: str = Field(..., min_length=1, max_length=32)
    api_key: SecretStr = Field(...)

    model_config = {"extra": "ignore"}

    @field_validator("provider")
    @classmethod
    def _provider_pulito(cls, value: str) -> str:
        pulito = value.strip().lower()
        if not pulito:
            raise ValueError("Il fornitore non puo essere vuoto.")
        return pulito

    @field_validator("api_key")
    @classmethod
    def _chiave_plausibile(cls, value: SecretStr) -> SecretStr:
        # La lunghezza si controlla sul valore segreto, ma il messaggio d'errore
        # non ne riporta MAI il contenuto.
        grezza = value.get_secret_value()
        pulita = grezza.strip()
        if len(pulita) < 8:
            raise ValueError("La chiave e troppo corta per essere una chiave valida.")
        if len(pulita) > 512:
            raise ValueError("La chiave e piu lunga di quanto qualunque fornitore preveda.")
        if pulita != grezza:
            return SecretStr(pulita)
        return value


class AiCredentialResponse(BaseModel):
    """Stato di UNA credenziale. La chiave non torna MAI indietro."""

    provider: str
    configured: bool
    # Ultime 4 cifre: servono solo a far riconoscere all'utente quale chiave ha
    # registrato. Non e la chiave e non basta a ricostruirla.
    key_hint: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AiCredentialListResponse(BaseModel):
    """Elenco dei fornitori per cui l'utente ha registrato una chiave."""

    items: list[AiCredentialResponse] = Field(default_factory=list)


class AiProviderHealth(BaseModel):
    """Un fornitore inoltrabile dal relay."""

    id: str
    label: str
    # Percorsi che il relay accetta di inoltrare per questo fornitore.
    allowed_paths: list[str] = Field(default_factory=list)


class AiHealthResponse(BaseModel):
    """Risposta di `GET /ai/health`.

    Serve a distinguere TRE guasti che si curano in tre modi diversi:
      - relay assente          -> questa rotta risponde 404 (il frontend lo
                                  riconosce gia: AI_PROXY_MISSING_MESSAGE);
      - relay presente ma non configurato -> `encryption_configured = false`:
                                  manca la chiave di cifratura lato server e
                                  nessuna credenziale puo essere registrata;
      - fornitore che rifiuta  -> il relay c'e ed e configurato, l'errore
                                  arriva dalla chiamata vera.
    """

    relay: bool = True
    enabled: bool = True
    encryption_configured: bool = False
    providers: list[AiProviderHealth] = Field(default_factory=list)
    # Tetto per utente applicato dal server (es. "30/minute").
    rate_limit: str = ""
    # Messaggio ITALIANO gia pronto da mostrare.
    message: str = ""
