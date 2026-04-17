# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/services/gex_service.py
# v3: + get_all_chains() per endpoint multi-expiry
#     + helper _is_monthly_expiry (3° venerdì del mese)
#     + helper _compute_dte_days (in giorni, precomputato server-side)
# ============================================================

from datetime import date, datetime, timezone, timedelta
from collections import defaultdict
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.repositories.gex_repository import GexRepository
from app.services.polygon_provider import OIProvider, TickerSnapshot
from app.schemas.gex import (
    StrikeGexData, GexChainResponse, GexExpiriesResponse,
    ExpiryChainData, GexAllChainsResponse,
)


NY_TZ = ZoneInfo("America/New_York")


def _today_ny() -> date:
    return datetime.now(NY_TZ).date()


def _is_monthly_expiry(d: date) -> bool:
    """
    True se `d` è il 3° venerdì del suo mese (convenzione 'monthly' US equity options).
    weekday() == 4 è venerdì. Il 3° venerdì cade sempre tra il 15 e il 21.
    """
    return d.weekday() == 4 and 15 <= d.day <= 21


def _compute_dte_days(expiry: date) -> float:
    """
    Giorni fino a scadenza, usando il close US (21:00 UTC = 16:00 ET).
    Ritorna float: 0.5 per scadenze oggi pomeridiane, 1.5 per domani, ecc.
    Minimo 0.5/365 (evita zero) — ma qui in giorni, quindi minimo 0.5/365*365 = 0.5 giorni, no, qui in giorni ritorno float min 0.5/24 (~30 min).
    Qui usiamo un minimo di 0.02 giorni (~30 min) per evitare edge case numerici.
    """
    expiry_dt = datetime(expiry.year, expiry.month, expiry.day, 21, 0, 0, tzinfo=timezone.utc)
    now_dt = datetime.now(timezone.utc)
    diff_seconds = (expiry_dt - now_dt).total_seconds()
    days = diff_seconds / 86400.0
    return max(0.02, days)


class GexService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = GexRepository(db)

    # ═══════════════════════════════════════════════
    # LETTURA
    # ═══════════════════════════════════════════════

    def _compute_flags(self, fetched_at: datetime | None, row_count: int) -> tuple[bool, bool]:
        if fetched_at is None or row_count == 0:
            return False, True
        fetched_ny = fetched_at.astimezone(NY_TZ).date()
        today_ny = _today_ny()
        return (fetched_ny < today_ny), False

    def get_chain(self, ticker: str, expiry: date) -> GexChainResponse:
        ticker = ticker.upper()
        last_fetched = self.repo.get_last_fetched_at(ticker)
        ticker_count = self.repo.count_for_ticker(ticker)
        is_prev, is_loading = self._compute_flags(last_fetched, ticker_count)

        if expiry < _today_ny():
            return GexChainResponse(
                ticker=ticker, expiry=expiry,
                fetched_at=last_fetched,
                is_previous_session=is_prev, is_loading=is_loading,
                strikes=[],
            )

        rows = self.repo.find_by_ticker_and_expiry(ticker, expiry)
        strikes = [
            StrikeGexData(
                strike=r.strike, oi_call=r.oi_call, oi_put=r.oi_put,
                iv_call=r.iv_call, iv_put=r.iv_put,
            )
            for r in rows
        ]

        return GexChainResponse(
            ticker=ticker, expiry=expiry,
            fetched_at=last_fetched,
            is_previous_session=is_prev, is_loading=is_loading,
            strikes=strikes,
        )

    def get_expiries(self, ticker: str) -> GexExpiriesResponse:
        ticker = ticker.upper()
        all_expiries = self.repo.get_distinct_expiries(ticker)
        last_fetched = self.repo.get_last_fetched_at(ticker)
        ticker_count = self.repo.count_for_ticker(ticker)
        is_prev, is_loading = self._compute_flags(last_fetched, ticker_count)

        today = _today_ny()
        future_expiries = [e for e in all_expiries if e >= today]

        return GexExpiriesResponse(
            ticker=ticker,
            fetched_at=last_fetched,
            is_previous_session=is_prev, is_loading=is_loading,
            expiries=future_expiries,
        )

    # ★ v3: multi-expiry
    def get_all_chains(self, ticker: str) -> GexAllChainsResponse:
        """
        Ritorna TUTTE le scadenze future con i loro strikes in un unico payload.
        Usato dal frontend per calcolare aggregati (All / 0DTE / Monthly)
        con una sola chiamata HTTP.

        Implementazione: 1 query per le scadenze + N query per gli strikes
        (una per scadenza). N è ~50 per SPX, ma si tratta di query rapidissime
        su indice (ticker, expiry) — tempo totale < 200ms in condizioni normali.
        """
        ticker = ticker.upper()
        last_fetched = self.repo.get_last_fetched_at(ticker)
        ticker_count = self.repo.count_for_ticker(ticker)
        is_prev, is_loading = self._compute_flags(last_fetched, ticker_count)

        all_expiries = self.repo.get_distinct_expiries(ticker)
        today = _today_ny()
        future_expiries = [e for e in all_expiries if e >= today]

        chains: list[ExpiryChainData] = []
        for exp in future_expiries:
            rows = self.repo.find_by_ticker_and_expiry(ticker, exp)
            if not rows:
                continue
            strikes = [
                StrikeGexData(
                    strike=r.strike, oi_call=r.oi_call, oi_put=r.oi_put,
                    iv_call=r.iv_call, iv_put=r.iv_put,
                )
                for r in rows
            ]
            chains.append(ExpiryChainData(
                expiry=exp,
                dte_days=_compute_dte_days(exp),
                is_monthly=_is_monthly_expiry(exp),
                strikes=strikes,
            ))

        return GexAllChainsResponse(
            ticker=ticker,
            fetched_at=last_fetched,
            is_previous_session=is_prev, is_loading=is_loading,
            expiries=chains,
        )

    # ═══════════════════════════════════════════════
    # SCRITTURA — invariata
    # ═══════════════════════════════════════════════

    @staticmethod
    def _aggregate_snapshot(snapshot: TickerSnapshot) -> list[dict]:
        aggregated: dict[tuple[date, float], dict] = defaultdict(
            lambda: {"oi_call": 0, "oi_put": 0, "iv_call": None, "iv_put": None}
        )

        for c in snapshot.contracts:
            key = (c.expiry, c.strike)
            bucket = aggregated[key]
            if c.contract_type == "call":
                bucket["oi_call"] = c.open_interest
                bucket["iv_call"] = c.implied_volatility
            elif c.contract_type == "put":
                bucket["oi_put"] = c.open_interest
                bucket["iv_put"] = c.implied_volatility

        rows = []
        for (expiry, strike), vals in aggregated.items():
            rows.append({
                "ticker": snapshot.ticker,
                "expiry": expiry,
                "strike": strike,
                "oi_call": vals["oi_call"],
                "oi_put": vals["oi_put"],
                "iv_call": vals["iv_call"],
                "iv_put": vals["iv_put"],
                "fetched_at": snapshot.fetched_at,
            })
        return rows

    async def refresh_ticker(self, ticker: str, provider: OIProvider) -> int:
        ticker = ticker.upper()
        print(f"[GEX] Starting refresh for {ticker} at {datetime.now(timezone.utc).isoformat()}")

        snapshot = await provider.fetch_ticker_snapshot(ticker)

        if not snapshot.contracts:
            print(f"[GEX] WARN: {ticker} snapshot is empty, skipping DB write to preserve old data")
            return 0

        rows = self._aggregate_snapshot(snapshot)
        if not rows:
            print(f"[GEX] WARN: {ticker} aggregated rows empty, skipping DB write")
            return 0

        inserted = self.repo.bulk_replace_ticker(ticker, rows)
        print(f"[GEX] {ticker}: {inserted} rows written (at {datetime.now(timezone.utc).isoformat()})")
        return inserted

    def has_todays_data(self, ticker: str) -> bool:
        last = self.repo.get_last_fetched_at(ticker.upper())
        if last is None:
            return False
        fetched_ny = last.astimezone(NY_TZ).date()
        today_ny = _today_ny()
        return fetched_ny >= today_ny

    def needs_bootstrap(self, ticker: str) -> bool:
        return self.repo.count_for_ticker(ticker.upper()) == 0