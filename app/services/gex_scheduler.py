# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/services/gex_scheduler.py
#
# v2: Loop di retry ogni minuto fino al successo + trigger manuale.
#
# Funzionamento:
# - Job giornaliero alle 15:35 Europe/Rome (5 min dopo l'open US) lun-ven.
#   Avvia, per ogni ticker, un loop asincrono che ritenta ogni 60s
#   finché has_todays_data(ticker) diventa True (oppure cutoff orario).
# - Job di safety net alle 15:50 e 16:10 (idempotenti: se il loop di un
#   ticker è già in corso, non avviano un secondo loop).
# - Bootstrap allo startup: stesso loop, così anche il primo fetch è
#   resiliente ai timeout.
# - trigger_manual_refresh(ticker): API per la nuova route POST manuale.
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

# Intervallo tra tentativi del loop di retry quando il fetch fallisce.
RETRY_INTERVAL_SECONDS = 60

# Smetti di riprovare dopo questa ora (Rome). 23:00 lascia ~7.5h dal main job.
RETRY_CUTOFF_HOUR = 23


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
        # Un task per ticker: previene loop duplicati se più job sovrapposti
        # tentano di partire contemporaneamente.
        self._running_loops: dict[str, asyncio.Task] = {}

    # ─── Provider factory (nuovo provider per ogni ciclo) ───

    def _new_provider(self) -> PolygonProvider:
        return PolygonProvider(
            api_key=self.polygon_api_key,
            rate_limit_per_minute=self.rate_limit_per_minute,
        )

    # ─── Loop di retry per un singolo ticker ───

    async def _refresh_loop_until_success(self, ticker: str, *, source: str) -> None:
        """
        Loop infinito (con cutoff): tenta refresh_ticker e ritenta ogni
        RETRY_INTERVAL_SECONDS finché has_todays_data(ticker) è True.

        Esce in 4 casi:
          1. has_todays_data(ticker) è True  → SUCCESS
          2. ora locale ≥ RETRY_CUTOFF_HOUR  → STOP per cutoff
          3. CancelledError (shutdown)        → STOP
        """
        attempt = 0
        while True:
            attempt += 1
            now_rome = datetime.now(ROME_TZ)
            ts = now_rome.strftime("%H:%M:%S")

            # Skip immediato se i dati di oggi sono già nel DB
            # (può succedere se un altro loop ci ha già preceduto, o
            # se la trigger manuale arriva dopo il main job riuscito).
            db = SessionLocal()
            try:
                if GexService(db).has_todays_data(ticker):
                    print(f"[GexScheduler] {ticker} ({source}): "
                          f"dati di oggi già presenti, loop terminato")
                    return
            finally:
                db.close()

            print(f"[GexScheduler] {ticker} ({source}): "
                  f"tentativo #{attempt} @ {ts} Rome")

            # Tenta il refresh
            db = SessionLocal()
            try:
                service = GexService(db)
                provider = self._new_provider()
                await service.refresh_ticker(ticker, provider)

                # Verifica esito reale: ha scritto dati di oggi?
                if service.has_todays_data(ticker):
                    print(f"[GexScheduler] {ticker} ({source}): "
                          f"SUCCESS al tentativo #{attempt}")
                    return
                else:
                    # Refresh ha completato ma snapshot vuoto / non scritto
                    print(f"[GexScheduler] {ticker} ({source}): "
                          f"tentativo #{attempt} senza dati di oggi (snapshot vuoto?)")
            except asyncio.CancelledError:
                print(f"[GexScheduler] {ticker} ({source}): loop cancellato")
                raise
            except Exception as e:
                print(f"[GexScheduler] {ticker} ({source}): "
                      f"tentativo #{attempt} ERRORE {type(e).__name__}: {e}")
            finally:
                db.close()

            # Cutoff orario: dopo RETRY_CUTOFF_HOUR smetti di riprovare
            now_rome = datetime.now(ROME_TZ)
            if now_rome.hour >= RETRY_CUTOFF_HOUR:
                print(f"[GexScheduler] {ticker} ({source}): "
                      f"cutoff {RETRY_CUTOFF_HOUR}:00 Rome raggiunto dopo "
                      f"{attempt} tentativi, stop")
                return

            print(f"[GexScheduler] {ticker} ({source}): "
                  f"ritento tra {RETRY_INTERVAL_SECONDS}s...")
            try:
                await asyncio.sleep(RETRY_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                print(f"[GexScheduler] {ticker} ({source}): cancellato durante attesa")
                raise

    def _start_loop_for_ticker(self, ticker: str, *, source: str) -> bool:
        """
        Avvia il loop per un ticker. Idempotente: se è già in corso,
        non avvia un secondo task. Ritorna True se avviato adesso.
        """
        existing = self._running_loops.get(ticker)
        if existing is not None and not existing.done():
            print(f"[GexScheduler] {ticker} ({source}): loop già in corso, skip")
            return False

        task = asyncio.create_task(
            self._refresh_loop_until_success(ticker, source=source),
            name=f"gex_loop_{ticker}",
        )
        self._running_loops[ticker] = task
        # Cleanup automatico al termine del task
        task.add_done_callback(lambda t, k=ticker: self._running_loops.pop(k, None))
        return True

    # ─── Job APScheduler (registrati nel cron) ───

    async def _job_kickoff(self, *, reason: str) -> None:
        now_rome = datetime.now(ROME_TZ).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[GexScheduler] ▶ KICKOFF ({reason}) @ {now_rome} Rome — "
              f"tickers: {self.tickers}")
        for ticker in self.tickers:
            self._start_loop_for_ticker(ticker, source=reason)

    async def _job_main(self) -> None:
        await self._job_kickoff(reason="main 15:35")

    async def _job_safety_15_50(self) -> None:
        await self._job_kickoff(reason="safety 15:50")

    async def _job_safety_16_10(self) -> None:
        await self._job_kickoff(reason="safety 16:10")

    # ─── Bootstrap al boot ───

    async def _bootstrap_if_needed(self) -> None:
        """
        All'avvio del backend: se un ticker ha 0 righe nel DB, avvia il
        loop di retry per fare il primo fetch (anche resiliente ai timeout).
        Se ha già dati (anche vecchi) non fare niente: il ciclo giornaliero
        li aggiornerà.
        """
        db = SessionLocal()
        try:
            service = GexService(db)
            to_bootstrap = [t for t in self.tickers if service.needs_bootstrap(t)]
        finally:
            db.close()

        if not to_bootstrap:
            print("[GexScheduler] Bootstrap: tutti i ticker hanno già dati, skip")
            return

        print(f"[GexScheduler] Bootstrap: avvio loop iniziale per {to_bootstrap}")
        for ticker in to_bootstrap:
            self._start_loop_for_ticker(ticker, source="bootstrap")

    # ═══════════════ API pubblica ═══════════════

    def trigger_manual_refresh(self, ticker: str) -> dict:
        """
        Chiamato dalla route POST manuale. Avvia il loop di retry per il
        ticker richiesto. Idempotente: se un loop è già in corso ritorna
        'already_running' senza creare un duplicato.
        """
        ticker_up = ticker.upper()
        if ticker_up not in self.tickers:
            return {
                "status": "unknown_ticker",
                "ticker": ticker_up,
                "available_tickers": self.tickers,
            }

        if not self.enabled or not self.polygon_api_key:
            return {
                "status": "disabled",
                "ticker": ticker_up,
                "message": "Scheduler GEX disattivato o POLYGON_API_KEY mancante",
            }

        started = self._start_loop_for_ticker(ticker_up, source="manual")
        return {
            "status": "started" if started else "already_running",
            "ticker": ticker_up,
        }

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

        # Main 15:35 Rome — avvia il loop di retry per tutti i ticker.
        self._scheduler.add_job(
            self._job_main,
            trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=ROME_TZ),
            id="gex_main",
            name="GEX main 15:35 Rome",
            misfire_grace_time=600,
            coalesce=True,
        )
        # Safety net 15:50 e 16:10: idempotenti (se il loop è già in corso,
        # non fanno niente). Servono solo se il main job non è partito affatto.
        self._scheduler.add_job(
            self._job_safety_15_50,
            trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=50, timezone=ROME_TZ),
            id="gex_safety_15_50",
            name="GEX safety 15:50 Rome",
            misfire_grace_time=600,
            coalesce=True,
        )
        self._scheduler.add_job(
            self._job_safety_16_10,
            trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=10, timezone=ROME_TZ),
            id="gex_safety_16_10",
            name="GEX safety 16:10 Rome",
            misfire_grace_time=600,
            coalesce=True,
        )

        self._scheduler.start()
        print(f"[GexScheduler] Avviato — tickers: {self.tickers}, "
              f"rate_limit={self.rate_limit_per_minute}/min, "
              f"retry_every={RETRY_INTERVAL_SECONDS}s, "
              f"cutoff={RETRY_CUTOFF_HOUR}:00 Rome")

        # Bootstrap in background (non blocca lo startup del backend)
        asyncio.create_task(self._bootstrap_if_needed())

    def shutdown(self) -> None:
        """Ferma lo scheduler. Da chiamare nel lifespan shutdown di FastAPI."""
        # Cancella i loop in corso per chiudere puliti
        for ticker, task in list(self._running_loops.items()):
            if not task.done():
                task.cancel()
        self._running_loops.clear()

        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            print("[GexScheduler] Fermato")


# ─── Istanza globale (popolata in main.py allo startup) ───

gex_scheduler: GexScheduler | None = None
