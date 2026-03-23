# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/services/tastytrade_service.py
# v6: timeout 60s per option chains grandi (SPX)
# ============================================================

import secrets
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.config import get_settings
from app.repositories.broker_token_repository import BrokerTokenRepository
from app.utils.encryption import encrypt_token, decrypt_token
from app.utils.exceptions import ForbiddenException

BROKER_ID = "tastytrade"
_pending_states: dict[str, dict] = {}


class TastyTradeService:
    def __init__(self, db: Session):
        self.db = db
        self.token_repo = BrokerTokenRepository(db)
        self.settings = get_settings()

    # ═══════════════ OAuth2 Flow (produzione) ═══════════════

    def get_auth_url(self, user_id: str) -> dict:
        state = secrets.token_urlsafe(32)
        _pending_states[state] = {
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        expired = [k for k, v in _pending_states.items()
                   if datetime.fromisoformat(v["created_at"]) < cutoff]
        for k in expired:
            del _pending_states[k]

        auth_url = (
             f"{self.settings.tastytrade_auth_url}/auth.html"
            f"?response_type=code"
            f"&client_id={self.settings.TASTYTRADE_CLIENT_ID}"
            f"&redirect_uri={self.settings.TASTYTRADE_REDIRECT_URI}"
            f"&scope=openid+read+trade"
            f"&state={state}"
        )
        return {"auth_url": auth_url, "state": state}

    async def handle_callback(self, code: str, state: str) -> dict:
        pending = _pending_states.pop(state, None)
        if not pending:
            raise ForbiddenException()

        user_id = pending["user_id"]

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self.settings.tastytrade_base_url}/oauth/token",
             json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.settings.TASTYTRADE_REDIRECT_URI,
                    "client_id": self.settings.TASTYTRADE_CLIENT_ID,
                    "client_secret": self.settings.TASTYTRADE_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )

        if resp.status_code not in (200, 201):
            print(f"[TT] OAuth callback failed: {resp.status_code} - {resp.text}")
            raise ForbiddenException()

        token_data = resp.json()
        access_token = (token_data.get("access_token")
                        or token_data.get("data", {}).get("session-token", "")
                        or token_data.get("data", {}).get("access_token", ""))
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in", 900)

        if not access_token:
            raise ForbiddenException()

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.token_repo.upsert(user_id, BROKER_ID, {
            "access_token_enc": encrypt_token(access_token),
            "refresh_token_enc": encrypt_token(refresh_token) if refresh_token else None,
            "expires_at": expires_at,
        })
        return {"success": True, "user_id": user_id}

    # ═══════════════ Sandbox: refresh token manuale ═══════════════

    async def save_refresh_token(self, user_id: str, refresh_token: str) -> dict:
        access_token, expires_in = await self._exchange_refresh_token(refresh_token)
        if not access_token:
            raise ForbiddenException()

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.token_repo.upsert(user_id, BROKER_ID, {
            "access_token_enc": encrypt_token(access_token),
            "refresh_token_enc": encrypt_token(refresh_token),
            "expires_at": expires_at,
        })
        return {"success": True, "expires_at": expires_at.isoformat()}

    # ═══════════════ Token Exchange & Refresh ═══════════════

    async def _exchange_refresh_token(self, refresh_token: str) -> tuple[str | None, int]:
        url = f"{self.settings.tastytrade_base_url}/oauth/token"
        print(f"[TT] Exchanging refresh token at: {url}")
        print(f"[TT] Client secret (first 12 chars): {self.settings.TASTYTRADE_CLIENT_SECRET[:12]}...")
        print(f"[TT] Refresh token (first 30 chars): {refresh_token[:30]}...")

        # Tentativo 1: JSON (come fa il SDK ufficiale tastyware)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_secret": self.settings.TASTYTRADE_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )

        if resp.status_code not in (200, 201):
            print(f"[TT] JSON attempt: {resp.status_code} - {resp.text}")
            # Tentativo 2: form-encoded
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_secret": self.settings.TASTYTRADE_CLIENT_SECRET,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                )

        if resp.status_code not in (200, 201):
            print(f"[TT] Form attempt: {resp.status_code} - {resp.text}")
            return None, 0

        print(f"[TT] Success! Status: {resp.status_code}")
        data = resp.json()
        print(f"[TT] Response keys: {list(data.keys())}")

        access_token = (data.get("access_token")
                        or data.get("data", {}).get("session-token", "")
                        or data.get("data", {}).get("access_token", "")
                        or data.get("data", {}).get("token", ""))
        expires_in = data.get("expires_in", 900)
        return access_token, expires_in

    async def refresh_access_token(self, user_id: str) -> str | None:
        token_row = self.token_repo.find_by_user_and_broker(user_id, BROKER_ID)
        if not token_row or not token_row.refresh_token_enc:
            return None

        refresh_tok = decrypt_token(token_row.refresh_token_enc)
        if not refresh_tok:
            return None

        access_token, expires_in = await self._exchange_refresh_token(refresh_tok)
        if not access_token:
            return None

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.token_repo.upsert(user_id, BROKER_ID, {
            "access_token_enc": encrypt_token(access_token),
            "expires_at": expires_at,
        })
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

    def disconnect(self, user_id: str) -> bool:
        return self.token_repo.delete_by_user_and_broker(user_id, BROKER_ID)

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
                raise Exception(f"TastyTrade API error {resp.status_code}: {resp.text[:500]}")
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

    async def search_symbols(self, user_id: str, query: str) -> list[dict]:
        data = await self._api_request(user_id, "GET", "/symbols/search/" + query)
        return data.get("data", {}).get("items", [])

    async def place_order(self, user_id: str, account_number: str, order: dict) -> dict:
        return await self._api_request(user_id, "POST", f"/accounts/{account_number}/orders", json_body=order)

    async def get_positions(self, user_id: str, account_number: str) -> list[dict]:
        data = await self._api_request(user_id, "GET", f"/accounts/{account_number}/positions")
        return data.get("data", {}).get("items", [])