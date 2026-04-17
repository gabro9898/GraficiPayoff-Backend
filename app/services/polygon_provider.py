# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/services/polygon_provider.py
# v9 FIX: paginazione manuale via strike_price.gt invece di next_url.
#
# Bug risolto: next_url di Polygon per snapshot opzioni INDEX non mantiene
# correttamente i filtri di query (expiration_date, contract_type).
# Le pagine successive "scivolavano" su altre expiry, corrompendo il fetch.
# I log diagnostici hanno mostrato che la pagina 2 di 2026-04-30 ritornava
# strike di 2026-04-17, causando troncamento a 250 contratti.
#
# Fix: ignoriamo next_url e paginiamo manualmente.
# Se la pagina ritorna == limit contratti, probabilmente c'è altra roba.
# Richiedi la prossima con strike_price.gt = max_strike_visto.
# ============================================================

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import httpx


# ═══════════════ Data model interno ═══════════════

@dataclass
class ContractData:
    strike: float
    expiry: date
    contract_type: str
    open_interest: int
    implied_volatility: float | None
    option_ticker: str = ""


@dataclass
class TickerSnapshot:
    ticker: str
    contracts: list[ContractData] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════ Interfaccia astratta ═══════════════

class OIProvider(ABC):
    @abstractmethod
    async def fetch_ticker_snapshot(self, ticker: str) -> TickerSnapshot:
        ...


# ═══════════════ Rate limiter ═══════════════

class AsyncRateLimiter:
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self.enabled = max_per_minute > 0
        self._lock = asyncio.Lock()
        self._calls: list[float] = []

    async def acquire(self) -> None:
        if not self.enabled:
            return
        async with self._lock:
            while True:
                now = time.monotonic()
                self._calls = [t for t in self._calls if now - t < 60.0]
                if len(self._calls) < self.max_per_minute:
                    self._calls.append(now)
                    return
                oldest = self._calls[0]
                wait_time = 60.0 - (now - oldest) + 0.05
                await asyncio.sleep(wait_time)


# ═══════════════ Implementazione Polygon ═══════════════

class PolygonProvider(OIProvider):
    BASE_URL = "https://api.polygon.io"
    INDEX_TICKERS = {"SPX", "NDX", "RUT", "VIX", "DJX", "XSP"}
    MAX_EXPIRATIONS = 200
    PAGE_LIMIT = 250         # limite hard di Polygon per snapshot
    MAX_PAGES_PER_CALL = 50  # safety: 50 × 250 = 12.500 strike per expiry+tipo

    def __init__(self, api_key: str, rate_limit_per_minute: int = 5, http_timeout: float = 30.0):
        self.api_key = api_key
        self.rate_limiter = AsyncRateLimiter(rate_limit_per_minute)
        self.http_timeout = http_timeout

    def _underlying_for_snapshot(self, ticker: str) -> str:
        ticker_up = ticker.upper()
        if ticker_up in self.INDEX_TICKERS:
            return f"I:{ticker_up}"
        return ticker_up

    @staticmethod
    def _parse_contract(item: dict[str, Any]) -> ContractData | None:
        details = item.get("details") or {}
        strike = details.get("strike_price")
        expiry_str = details.get("expiration_date")
        contract_type = details.get("contract_type")
        option_ticker = details.get("ticker", "")

        if strike is None or not expiry_str or contract_type not in ("call", "put"):
            return None

        try:
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        except ValueError:
            return None

        oi_raw = item.get("open_interest")
        try:
            oi = int(oi_raw) if oi_raw is not None else 0
        except (TypeError, ValueError):
            oi = 0

        iv_raw = item.get("implied_volatility")
        try:
            iv = float(iv_raw) if iv_raw is not None else None
        except (TypeError, ValueError):
            iv = None

        return ContractData(
            strike=float(strike),
            expiry=expiry,
            contract_type=contract_type,
            open_interest=oi,
            implied_volatility=iv,
            option_ticker=option_ticker,
        )

    # ─── Step 1: discovery scadenze ───

    async def _discover_expirations(
        self, client: httpx.AsyncClient, underlying: str
    ) -> list[str]:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        expirations: list[str] = []

        gt_param = "expiration_date.gte"
        cursor_date = today_str
        url = f"{self.BASE_URL}/v3/snapshot/options/{underlying}"

        for _ in range(self.MAX_EXPIRATIONS):
            params = {
                gt_param: cursor_date,
                "limit": 1,
                "order": "asc",
                "sort": "expiration_date",
                "apiKey": self.api_key,
            }

            await self.rate_limiter.acquire()
            resp = await client.get(url, params=params)

            if resp.status_code == 429:
                await asyncio.sleep(30)
                continue
            if resp.status_code != 200:
                print(f"[Polygon] discover HTTP {resp.status_code}: {resp.text[:200]}")
                raise RuntimeError(f"Polygon discover HTTP {resp.status_code}")

            results = (resp.json().get("results") or [])
            if not results:
                break

            exp_str = (results[0].get("details") or {}).get("expiration_date")
            if not exp_str or exp_str in expirations:
                break

            expirations.append(exp_str)
            gt_param = "expiration_date.gt"
            cursor_date = exp_str

        return expirations

    # ─── Step 2: snapshot per (scadenza, contract_type) con paginazione manuale ───

    async def _fetch_expiry_by_type(
        self,
        client: httpx.AsyncClient,
        underlying: str,
        expiration_date: str,
        contract_type: str,
    ) -> list[ContractData]:
        """
        Fetch contratti per UNA scadenza filtrati per tipo (call o put).

        ★ v9: paginazione manuale via strike_price.gt invece di next_url.
        Questo perché next_url di Polygon per snapshot indici non mantiene
        i filtri expiration_date/contract_type e può "scivolare" su altre
        expiry, corrompendo il fetch.

        Logica:
          - Prima pagina: strike_price.gt=0, ordinato per strike asc
          - Se ricevi == PAGE_LIMIT risultati, richiedi la prossima con
            strike_price.gt = max_strike_visto
          - Stop quando ricevi < PAGE_LIMIT risultati (fine dati)
        """
        url = f"{self.BASE_URL}/v3/snapshot/options/{underlying}"

        contracts: list[ContractData] = []
        seen_tickers: set[str] = set()
        last_strike_seen = 0.0
        pages = 0

        while pages < self.MAX_PAGES_PER_CALL:
            params: dict[str, Any] = {
                "expiration_date": expiration_date,
                "contract_type": contract_type,
                "strike_price.gt": last_strike_seen,
                "order": "asc",
                "sort": "strike_price",
                "limit": self.PAGE_LIMIT,
                "apiKey": self.api_key,
            }

            await self.rate_limiter.acquire()
            resp = await client.get(url, params=params)

            if resp.status_code == 429:
                await asyncio.sleep(30)
                continue
            if resp.status_code != 200:
                print(f"[Polygon] snapshot {expiration_date}/{contract_type} "
                      f"HTTP {resp.status_code} body={resp.text[:300]}")
                raise RuntimeError(f"Polygon snapshot HTTP {resp.status_code}")

            data = resp.json()
            results = data.get("results") or []

            new_on_page = 0
            max_strike_on_page = last_strike_seen
            wrong_expiry_count = 0
            wrong_type_count = 0

            for item in results:
                parsed = self._parse_contract(item)
                if parsed is None:
                    continue

                # ★ Safety check: scarta qualsiasi contratto che Polygon ritorna
                # e che NON corrisponde ai filtri richiesti (difesa contro bug API)
                if parsed.expiry.isoformat() != expiration_date:
                    wrong_expiry_count += 1
                    continue
                if parsed.contract_type != contract_type:
                    wrong_type_count += 1
                    continue

                if parsed.option_ticker and parsed.option_ticker in seen_tickers:
                    continue
                if parsed.option_ticker:
                    seen_tickers.add(parsed.option_ticker)

                contracts.append(parsed)
                new_on_page += 1
                if parsed.strike > max_strike_on_page:
                    max_strike_on_page = parsed.strike

            pages += 1

            if wrong_expiry_count > 0 or wrong_type_count > 0:
                print(f"[Polygon] {expiration_date}/{contract_type} page={pages} "
                      f"WARN scartati {wrong_expiry_count} wrong_expiry, "
                      f"{wrong_type_count} wrong_type")

            # Stop conditions:
            # 1. Ho ricevuto meno di PAGE_LIMIT risultati → fine dati per questa expiry
            # 2. Nessun nuovo contratto valido in questa pagina → loop guard
            # 3. max_strike non è avanzato → paginazione stalla
            if len(results) < self.PAGE_LIMIT:
                break
            if new_on_page == 0:
                break
            if max_strike_on_page <= last_strike_seen:
                print(f"[Polygon] {expiration_date}/{contract_type} page={pages} "
                      f"WARN strike non avanza ({last_strike_seen} → {max_strike_on_page}), stop")
                break

            last_strike_seen = max_strike_on_page

        return contracts

    # ─── Orchestrazione ───

    async def fetch_ticker_snapshot(self, ticker: str) -> TickerSnapshot:
        underlying = self._underlying_for_snapshot(ticker)
        t_start = time.monotonic()

        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            expirations = await self._discover_expirations(client, underlying)
            if not expirations:
                print(f"[Polygon] WARN: nessuna scadenza trovata per {ticker}")
                return TickerSnapshot(ticker=ticker.upper(), contracts=[])

            all_contracts: list[ContractData] = []
            for exp in expirations:
                try:
                    calls = await self._fetch_expiry_by_type(client, underlying, exp, "call")
                    puts = await self._fetch_expiry_by_type(client, underlying, exp, "put")
                    all_contracts.extend(calls)
                    all_contracts.extend(puts)
                except Exception as e:
                    print(f"[Polygon] {ticker} {exp}: ERRORE {type(e).__name__}: {e}")
                    continue

        elapsed = time.monotonic() - t_start
        unique_expiries = set(c.expiry for c in all_contracts)
        n_calls = sum(1 for c in all_contracts if c.contract_type == "call")
        n_puts = sum(1 for c in all_contracts if c.contract_type == "put")
        print(f"[Polygon] {ticker}: {len(all_contracts)} contratti "
              f"({n_calls} call + {n_puts} put) su {len(unique_expiries)} scadenze "
              f"in {elapsed:.1f}s")

        return TickerSnapshot(
            ticker=ticker.upper(),
            contracts=all_contracts,
            fetched_at=datetime.now(timezone.utc),
        )