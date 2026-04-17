# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/services/gex_scheduler.py
#
# Scheduler APScheduler per il refresh giornaliero del GEX.
# - Main job: 15:35 Europe/Rome (5 min dopo l'open US)
# - Retry 1:  15:50 (solo se il main è fallito / dati non ancora di oggi)
# - Retry 2:  16:10 (ultimo tentativo)
# - Bootstrap: all'avvio del backend, se il DB è vuoto per un ticker,
#   fetch immediato in background (non blocca lo startup)
# ============================================================

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.services.gex_service import GexService
from app.services.polygon_provider import PolygonProvider


ROME_TZ = ZoneInfo("Europe/Rome")


class GexScheduler:
    """
    Incapsula APScheduler + logica di refresh multi-ticker.
    Istanziato una sola volta nel lifespan di FastAPI (in main.py).
    """

    def __init__(
        self,
        tickers: list[str],
        polygon_api_key: str,
        rate_limit_per_minute: int,
        enabled: bool = True,
    ):
        self.tickers = [t.upper() for t in tickers if t.strip()]
        self.polygon_api_key = polygon_api_key
        self.rate_limit_per_minute = rate_limit_per_minute
        self.enabled = enabled
        self._scheduler: AsyncIOScheduler | None = None

    # ─── Provider factory (nuovo provider per ogni ciclo) ───

    def _new_provider(self) -> PolygonProvider:
        return PolygonProvider(
            api_key=self.polygon_api_key,
            rate_limit_per_minute=self.rate_limit_per_minute,
        )

    # ─── Job: refresh di un singolo ticker ───

    async def _refresh_ticker_safe(self, ticker: str, *, skip_if_has_todays_data: bool) -> None:
        """
        Refresh sicuro di un ticker. Apre una sessione DB dedicata.
        Logga e swallow-a le eccezioni (lo scheduler deve restare vivo).
        """
        db = SessionLocal()
        try:
            service = GexService(db)

            if skip_if_has_todays_data and service.has_todays_data(ticker):
                print(f"[GexScheduler] {ticker}: dati di oggi già presenti, skip")
                return

            provider = self._new_provider()
            await service.refresh_ticker(ticker, provider)
        except Exception as e:
            print(f"[GexScheduler] ERRORE refresh {ticker}: {type(e).__name__}: {e}")
        finally:
            db.close()

    # ─── Job: refresh di tutti i ticker configurati ───

    async def _refresh_all(self, *, skip_if_has_todays_data: bool, reason: str) -> None:
        now_rome = datetime.now(ROME_TZ).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[GexScheduler] ▶ RUN ({reason}) @ {now_rome} Rome — tickers: {self.tickers}")
        for ticker in self.tickers:
            await self._refresh_ticker_safe(ticker, skip_if_has_todays_data=skip_if_has_todays_data)
        print(f"[GexScheduler] ■ END ({reason})")

    # ─── Wrappers per APScheduler (sono i job registrati) ───

    async def _job_main(self) -> None:
        # Main run: non skippare (è la prima occasione della giornata, vogliamo dati freschi)
        await self._refresh_all(skip_if_has_todays_data=False, reason="main 15:35")

    async def _job_retry_1(self) -> None:
        # Retry solo se il main non ha scritto dati di oggi
        await self._refresh_all(skip_if_has_todays_data=True, reason="retry 15:50")

    async def _job_retry_2(self) -> None:
        await self._refresh_all(skip_if_has_todays_data=True, reason="retry 16:10")

    # ─── Bootstrap al boot ───

    async def _bootstrap_if_needed(self) -> None:
        """
        All'avvio del backend: se un ticker ha 0 righe nel DB, fai fetch immediato.
        Se ha già dati (anche vecchi) non fare niente: il ciclo giornaliero li aggiornerà.
        """
        db = SessionLocal()
        try:
            service = GexService(db)
            to_bootstrap = [t for t in self.tickers if service.needs_bootstrap(t)]
        finally:
            db.close()

        if not to_bootstrap:
            print(f"[GexScheduler] Bootstrap: tutti i ticker hanno già dati, skip")
            return

        print(f"[GexScheduler] Bootstrap: fetch iniziale per {to_bootstrap}")
        for ticker in to_bootstrap:
            await self._refresh_ticker_safe(ticker, skip_if_has_todays_data=False)

    # ═══════════════ API pubblica ═══════════════

    def start(self) -> None:
        """Configura e avvia lo scheduler. Da chiamare nel lifespan startup di FastAPI."""
        if not self.enabled:
            print("[GexScheduler] GEX_ENABLED=False — scheduler disattivato")
            return

        if not self.polygon_api_key:
            print("[GexScheduler] POLYGON_API_KEY non configurata — scheduler non avviato")
            return

        if not self.tickers:
            print("[GexScheduler] GEX_TICKERS vuoto — scheduler non avviato")
            return

        self._scheduler = AsyncIOScheduler(timezone=ROME_TZ)

        # Main 15:35 Rome, lun-ven (il mercato US è aperto solo nei giorni feriali)
        self._scheduler.add_job(
            self._job_main,
            trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=ROME_TZ),
            id="gex_main",
            name="GEX main refresh 15:35 Rome",
            misfire_grace_time=600,  # se manca il fire per max 10 min, recuperalo
            coalesce=True,
        )
        self._scheduler.add_job(
            self._job_retry_1,
            trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=50, timezone=ROME_TZ),
            id="gex_retry_1",
            name="GEX retry 15:50 Rome",
            misfire_grace_time=600,
            coalesce=True,
        )
        self._scheduler.add_job(
            self._job_retry_2,
            trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=10, timezone=ROME_TZ),
            id="gex_retry_2",
            name="GEX retry 16:10 Rome",
            misfire_grace_time=600,
            coalesce=True,
        )

        self._scheduler.start()
        print(f"[GexScheduler] Avviato — tickers: {self.tickers}, rate_limit={self.rate_limit_per_minute}/min")

        # Bootstrap in background (non blocca lo startup del backend)
        asyncio.create_task(self._bootstrap_if_needed())

    def shutdown(self) -> None:
        """Ferma lo scheduler. Da chiamare nel lifespan shutdown di FastAPI."""
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            print("[GexScheduler] Fermato")


# ─── Istanza globale (popolata in main.py allo startup) ───

gex_scheduler: GexScheduler | None = None