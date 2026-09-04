# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/services/tastytrade_service.py
# v7: Trusted Partner OAuth2 multi-tenant.
#   - state persistito su Postgres (oauth_states) → multi-worker safe
#   - URL-encode dei parametri authorize
#   - Fallback form-encoded anche sul primo token exchange
#   - Salva refresh_token ruotato (se TT lo restituisce)
#   - Disconnect chiama anche /oauth/revoke (best-effort)
# ============================================================

import asyncio
import secrets
import httpx
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.config import get_settings
from app.repositories.broker_token_repository import BrokerTokenRepository
from app.repositories.oauth_state_repository import OAuthStateRepository
from app.utils.encryption import encrypt_token, decrypt_token
from app.utils.exceptions import ForbiddenException, TastyTradeApiException

BROKER_ID = "tastytrade"

# Lunghezza massima del messaggio di errore riportato al client: il corpo di TT
# puo' contenere un elenco lungo di validazioni, e finisce dentro un JSON.
_MAX_DETAIL = 500


def _tastytrade_error_detail(resp: httpx.Response) -> str:
    """Il motivo del rifiuto, in forma leggibile, dalla risposta di TastyTrade.

    TT risponde con {"error": {"code": ..., "message": ..., "errors": [...]}}.
    Si prende `message`, aggiungendo le voci di `errors` quando ci sono (e' li'
    che finiscono i dettagli utili tipo "price must be a multiple of 0.05").
    Se il corpo non e' JSON — pagina HTML di un gateway, risposta vuota — si
    ripiega sul testo grezzo, che e' comunque meglio di niente.
    """
    try:
        body = resp.json()
    except Exception:
        body = None

    messaggio = None
    if isinstance(body, dict):
        errore = body.get("error")
        if isinstance(errore, dict):
            messaggio = errore.get("message")
            voci = errore.get("errors")
            if isinstance(voci, list):
                dettagli = [
                    v.get("message") for v in voci
                    if isinstance(v, dict) and v.get("message")
                ]
                if dettagli:
                    unito = "; ".join(dettagli)
                    messaggio = f"{messaggio}: {unito}" if messaggio else unito

    if not messaggio:
        messaggio = (resp.text or "").strip() or "nessun dettaglio nella risposta"

    return f"TastyTrade API error {resp.status_code}: {messaggio}"[:_MAX_DETAIL]

# ★ Lock per user_id sul refresh token. Evita che chiamate API parallele dello
# stesso utente scatenino N refresh simultanei: TT invalida il refresh_token
# dopo il primo uso, le altre chiamate fallirebbero 4xx. Con il lock,
# la prima richiesta refresha; le altre attendono e poi leggono il token
# rinnovato dal DB invece di rifare il refresh.
_refresh_locks: dict[str, asyncio.Lock] = {}


def _get_refresh_lock(user_id: str) -> asyncio.Lock:
    lock = _refresh_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _refresh_locks[user_id] = lock
    return lock


class TastyTradeService:
    def __init__(self, db: Session):
        self.db = db
        self.token_repo = BrokerTokenRepository(db)
        self.state_repo = OAuthStateRepository(db)
        self.settings = get_settings()

    # ═══════════════ OAuth2 Flow (produzione) ═══════════════

    def get_auth_url(self, user_id: str) -> dict:
        # Cleanup opportunistico di state scaduti (best-effort, errori ignorati)
        try:
            self.state_repo.cleanup_expired()
        except Exception as e:
            print(f"[TT] cleanup_expired failed (ignored): {e}")

        state = secrets.token_urlsafe(32)
        self.state_repo.create(state=state, user_id=user_id, broker_id=BROKER_ID)

        params = {
            "response_type": "code",
            "client_id": self.settings.TASTYTRADE_CLIENT_ID,
            "redirect_uri": self.settings.TASTYTRADE_REDIRECT_URI,
            # Scope concessi sulla dashboard TastyTrade per l'app Option Tracker.
            # Solo "read" e "trade" — niente "openid" (non abilitato per quest'app).
            "scope": "read trade",
            "state": state,
        }
        auth_url = f"{self.settings.tastytrade_auth_url}/auth.html?{urlencode(params)}"
        return {"auth_url": auth_url, "state": state}

    async def handle_callback(self, code: str, state: str) -> dict:
        pending = self.state_repo.pop(state, BROKER_ID)
        if pending is None:
            raise ForbiddenException()

        user_id = pending.user_id
        access_token, refresh_token, expires_in = await self._exchange_code_for_token(code)

        if not access_token:
            raise ForbiddenException()

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.token_repo.upsert(user_id, BROKER_ID, {
            "access_token_enc": encrypt_token(access_token),
            "refresh_token_enc": encrypt_token(refresh_token) if refresh_token else None,
            "expires_at": expires_at,
        })
        return {"success": True, "user_id": user_id}

    async def _exchange_code_for_token(self, code: str) -> tuple[str | None, str | None, int]:
        """Scambia authorization_code → (access_token, refresh_token, expires_in).
        Tenta JSON poi form-encoded per resilienza."""
        url = f"{self.settings.tastytrade_base_url}/oauth/token"
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.TASTYTRADE_REDIRECT_URI,
            "client_id": self.settings.TASTYTRADE_CLIENT_ID,
            "client_secret": self.settings.TASTYTRADE_CLIENT_SECRET,
        }

        # Tentativo 1: JSON
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url, json=body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )

        if resp.status_code not in (200, 201):
            print(f"[TT] code exchange JSON failed: {resp.status_code} - {resp.text[:300]}")
            # Tentativo 2: form-encoded
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url, data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                )

        if resp.status_code not in (200, 201):
            print(f"[TT] code exchange form failed: {resp.status_code} - {resp.text[:300]}")
            return None, None, 0

        data = resp.json()
        access_token = (data.get("access_token")
                        or data.get("data", {}).get("session-token", "")
                        or data.get("data", {}).get("access_token", ""))
        refresh_token = data.get("refresh_token", "") or None
        expires_in = data.get("expires_in", 900)
        return access_token, refresh_token, expires_in

    # ═══════════════ Sandbox: refresh token manuale ═══════════════

    async def save_refresh_token(self, user_id: str, refresh_token: str) -> dict:
        access_token, new_refresh, expires_in, _permanent = await self._exchange_refresh_token(refresh_token)
        if not access_token:
            raise ForbiddenException()

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.token_repo.upsert(user_id, BROKER_ID, {
            "access_token_enc": encrypt_token(access_token),
            # Se TT ha ruotato il refresh, salvo quello nuovo; altrimenti quello passato dall'utente.
            "refresh_token_enc": encrypt_token(new_refresh or refresh_token),
            "expires_at": expires_at,
        })
        return {"success": True, "expires_at": expires_at.isoformat()}

    # ═══════════════ Token Exchange & Refresh ═══════════════

    async def _exchange_refresh_token(self, refresh_token: str) -> tuple[str | None, str | None, int, bool]:
        """Scambia refresh_token → (access_token, new_refresh_token, expires_in, permanent_failure).
        new_refresh_token può essere None se TT non lo ruota.
        permanent_failure=True quando il refresh_token NON È PIÙ VALIDO (es. TT
        ha disattivato il grant per nuovo OAuth login dell'utente). Il caller
        in tal caso deve cancellare il token dal DB — ritentare con lo stesso
        token è inutile, serve nuovo OAuth login."""
        url = f"{self.settings.tastytrade_base_url}/oauth/token"
        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_secret": self.settings.TASTYTRADE_CLIENT_SECRET,
        }

        # Tentativo 1: JSON (come fa il SDK ufficiale tastyware)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url, json=body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )

        if resp.status_code not in (200, 201):
            print(f"[TT] refresh JSON failed: {resp.status_code} - {resp.text[:300]}")
            # Tentativo 2: form-encoded
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url, data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                )

        if resp.status_code not in (200, 201):
            print(f"[TT] refresh form failed: {resp.status_code} - {resp.text[:300]}")
            # ★ Distinguiamo errore permanente da transient. Permanente: 4xx
            # con "invalid_grant" o "Grant deactivated" nel body → refresh token
            # non più valido, serve nuovo OAuth login.
            body_lower = (resp.text or '').lower()
            is_permanent = (
                400 <= resp.status_code < 500 and
                ("invalid_grant" in body_lower or "grant deactivated" in body_lower)
            )
            return None, None, 0, is_permanent

        data = resp.json()
        access_token = (data.get("access_token")
                        or data.get("data", {}).get("session-token", "")
                        or data.get("data", {}).get("access_token", "")
                        or data.get("data", {}).get("token", ""))
        new_refresh = data.get("refresh_token", "") or None
        expires_in = data.get("expires_in", 900)
        return access_token, new_refresh, expires_in, False

    async def refresh_access_token(self, user_id: str) -> str | None:
        # ★ Serializza i refresh per user con un lock asyncio. Vedi commento
        # su _refresh_locks in cima al file per il razionale.
        async with _get_refresh_lock(user_id):
            token_row = self.token_repo.find_by_user_and_broker(user_id, BROKER_ID)
            if not token_row or not token_row.refresh_token_enc:
                return None

            # Double-check: se nel frattempo (mentre attendevamo il lock) un altro
            # task ha già rinnovato il token, restituiamolo direttamente senza
            # rifare il refresh — il refresh_token che vediamo qui potrebbe
            # essere già stato invalidato dall'altro task.
            if token_row.expires_at and token_row.expires_at > datetime.now(timezone.utc) + timedelta(seconds=30):
                fresh = decrypt_token(token_row.access_token_enc)
                if fresh:
                    return fresh

            refresh_tok = decrypt_token(token_row.refresh_token_enc)
            if not refresh_tok:
                return None

            access_token, new_refresh, expires_in, permanent_failure = await self._exchange_refresh_token(refresh_tok)
            if not access_token:
                # ★ Errore permanente (Grant deactivated, invalid_grant) → il
                # refresh non funzionerà mai più. Cancelliamo il token dal DB
                # così get_status() ritorna "connected: false" e il frontend
                # offre nuovo OAuth login.
                if permanent_failure:
                    print(f"[TT] refresh permanent failure for user {user_id} — clearing stored token")
                    self.token_repo.delete_by_user_and_broker(user_id, BROKER_ID)
                return None

            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            update: dict = {
                "access_token_enc": encrypt_token(access_token),
                "expires_at": expires_at,
            }
            # Se TT ruota il refresh, persistiamo subito quello nuovo (altrimenti
            # al refresh successivo useremmo uno revocato e perderemmo l'utente).
            if new_refresh:
                update["refresh_token_enc"] = encrypt_token(new_refresh)
            self.token_repo.upsert(user_id, BROKER_ID, update)
            return access_token

    # ═══════════════ Token Helpers ═══════════════

    async def get_valid_token(self, user_id: str) -> str:
        token_row = self.token_repo.find_by_user_and_broker(user_id, BROKER_ID)
        if not token_row:
            raise ForbiddenException()

        if token_row.expires_at and token_row.expires_at < datetime.now(timezone.utc):
            new_token = await self.refresh_access_token(user_id)
            if not new_token:
                raise ForbiddenException()
            return new_token

        decrypted = decrypt_token(token_row.access_token_enc)
        if not decrypted:
            raise ForbiddenException()
        return decrypted

    def get_status(self, user_id: str) -> dict:
        token_row = self.token_repo.find_by_user_and_broker(user_id, BROKER_ID)
        if not token_row:
            return {"broker_id": BROKER_ID, "connected": False, "expires_at": None}
        expired = token_row.expires_at and token_row.expires_at < datetime.now(timezone.utc)
        has_refresh = token_row.refresh_token_enc is not None
        return {
            "broker_id": BROKER_ID,
            "connected": not expired or has_refresh,
            "expires_at": token_row.expires_at,
        }

    async def disconnect(self, user_id: str) -> bool:
        """Revoca lato TastyTrade (best-effort) e cancella il record locale."""
        token_row = self.token_repo.find_by_user_and_broker(user_id, BROKER_ID)
        if token_row is not None:
            # Best-effort revoke: se TT non risponde, procedo comunque col delete locale.
            # Tentiamo a revocare sia access che refresh (alcuni provider revocano l'intera grant).
            for enc_field in (token_row.refresh_token_enc, token_row.access_token_enc):
                if not enc_field:
                    continue
                tok = decrypt_token(enc_field)
                if not tok:
                    continue
                try:
                    await self._revoke_token(tok)
                except Exception as e:
                    print(f"[TT] revoke failed (ignored): {e}")
        return self.token_repo.delete_by_user_and_broker(user_id, BROKER_ID)

    async def _revoke_token(self, token: str) -> None:
        """Chiama l'endpoint OAuth2 revoke standard. Se TT non lo espone, fallisce
        silenziosamente — il delete locale viene comunque eseguito dal caller."""
        url = f"{self.settings.tastytrade_base_url}/oauth/revoke"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                data={"token": token, "client_id": self.settings.TASTYTRADE_CLIENT_ID,
                      "client_secret": self.settings.TASTYTRADE_CLIENT_SECRET},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code >= 400:
            # OAuth2 RFC 7009: revoke ritorna 200 sia se il token esisteva sia se no.
            # 4xx/5xx → l'endpoint o non esiste o ha avuto un problema. Logghiamo, non re-raise.
            print(f"[TT] revoke status {resp.status_code}: {resp.text[:200]}")

    # ═══════════════ API Proxy ═══════════════

    async def _api_request(self, user_id: str, method: str, path: str,
                           params: dict | None = None, json_body: dict | None = None) -> dict:
        token = await self.get_valid_token(user_id)
        url = f"{self.settings.tastytrade_base_url}{path}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.request(method, url, headers=headers, params=params, json=json_body)
            if resp.status_code == 401:
                new_token = await self.refresh_access_token(user_id)
                if not new_token:
                    raise ForbiddenException()
                headers["Authorization"] = f"Bearer {new_token}"
                resp = await client.request(method, url, headers=headers, params=params, json=json_body)
            if resp.status_code >= 400:
                # ★ HTTPException, non Exception nuda: cosi' la risposta passa
                #   dall'ExceptionMiddleware (che sta DENTRO il CORS middleware)
                #   e arriva al client come JSON {"detail": ...} leggibile,
                #   invece che come 500 in testo semplice senza header CORS —
                #   che il browser scarta come errore di rete.
                #   Lo status esposto NON e' sempre quello di TT: vedi la
                #   docstring di TastyTradeApiException (401 e 403 hanno un
                #   significato per il frontend e vanno rimappati su 502).
                raise TastyTradeApiException(
                    resp.status_code, _tastytrade_error_detail(resp)
                )
            return resp.json()

    async def get_accounts(self, user_id: str) -> list[dict]:
        data = await self._api_request(user_id, "GET", "/customers/me/accounts")
        items = data.get("data", {}).get("items", [])
        return [{"account_number": i.get("account", {}).get("account-number", ""),
                 "account_type": i.get("account", {}).get("account-type-name", ""),
                 "nickname": i.get("account", {}).get("nickname", ""),
                 "is_margin": i.get("account", {}).get("margin-or-cash") == "Margin"} for i in items]

    async def get_streamer_token(self, user_id: str) -> dict:
        data = await self._api_request(user_id, "GET", "/api-quote-tokens")
        d = data.get("data", {})
        return {"token": d.get("token", ""), "dxlink_url": d.get("dxlink-url", ""), "level": d.get("level", "")}

    async def get_option_chains(self, user_id: str, symbol: str) -> dict:
        return await self._api_request(user_id, "GET", f"/option-chains/{symbol}/nested")

    # ─── Futures ───────────────────────────────────────────────────────────
    # TT distingue futures (es. /ES, /NQ, /CL) dalle equity. Endpoint diversi:
    # - lista contratti per product code: /instruments/futures?product-code=ES
    # - option chain del future:          /futures-option-chains/{symbol}/nested

    async def get_futures(self, user_id: str, product_code: str) -> list[dict]:
        """Lista contratti future per un product code (es. 'ES' o '/ES').
        Ritorna tutti i mesi disponibili — il client filtrerà i front month."""
        code = product_code.lstrip("/").upper()
        data = await self._api_request(
            user_id, "GET", "/instruments/futures", params={"product-code": code}
        )
        items = data.get("data", {}).get("items", [])
        return [{
            "symbol": i.get("symbol"),                       # es. "/ESM6"
            "active_month": i.get("active-month", False),
            "expiration_date": i.get("expiration-date"),     # YYYY-MM-DD
            "streamer_symbol": i.get("streamer-symbol"),     # per DXFeed quote
            "exchange": i.get("exchange"),
            "product_code": i.get("product-code"),
            "contract_size": i.get("notional-multiplier"),
            "product_name": i.get("product", {}).get("description") if isinstance(i.get("product"), dict) else None,
        } for i in items]

    async def get_future_option_chains(self, user_id: str, symbol: str) -> dict:
        """Option chain nested di un future product (es. 'ES' o '/ES').
        Nota: TT vuole il root code senza lo slash davanti nel path URL."""
        sym = symbol.lstrip("/").upper()
        return await self._api_request(
            user_id, "GET", f"/futures-option-chains/{sym}/nested"
        )

    async def search_symbols(self, user_id: str, query: str) -> list[dict]:
        data = await self._api_request(user_id, "GET", "/symbols/search/" + query)
        return data.get("data", {}).get("items", [])

    async def place_order(self, user_id: str, account_number: str, order: dict) -> dict:
        return await self._api_request(user_id, "POST", f"/accounts/{account_number}/orders", json_body=order)

    async def get_positions(self, user_id: str, account_number: str) -> list[dict]:
        data = await self._api_request(user_id, "GET", f"/accounts/{account_number}/positions")
        return data.get("data", {}).get("items", [])
