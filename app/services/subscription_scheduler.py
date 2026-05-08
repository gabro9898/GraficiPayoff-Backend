# ============================================================
# ★ BACKEND — FILE NUOVO
# Percorso: app/services/subscription_scheduler.py
#
# Scheduler dedicato agli abbonamenti. Indipendente dal GEX scheduler.
#
# Job 1: ogni 15 minuti, controlla cambi di subscription_expiry e manda
#        l'email "pagamento ricevuto" (intercetta sia webhook Stripe sia
#        edit manuali al DB).
# Job 2: ogni giorno alle 09:00 Europe/Rome, manda i promemoria 7/3/2/1
#        giorni prima della scadenza.
# ============================================================

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import SessionLocal
from app.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

ROME_TZ = ZoneInfo("Europe/Rome")

CHANGE_DETECTION_INTERVAL_MINUTES = 15
REMINDER_HOUR_ROME = 9


class SubscriptionScheduler:
    """Incapsula APScheduler per i job legati agli abbonamenti.
    Istanziato una sola volta nel lifespan di FastAPI (in main.py).
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._scheduler: AsyncIOScheduler | None = None

    def start(self) -> None:
        if not self.enabled:
            logger.info("[SubscriptionScheduler] Disabilitato via config, skip.")
            return
        if self._scheduler is not None:
            return  # Già avviato, idempotente

        self._scheduler = AsyncIOScheduler(timezone=ROME_TZ)

        self._scheduler.add_job(
            self._job_subscription_changes,
            IntervalTrigger(minutes=CHANGE_DETECTION_INTERVAL_MINUTES),
            id="subscription_changes",
            replace_existing=True,
            misfire_grace_time=300,
        )

        self._scheduler.add_job(
            self._job_expiry_reminders,
            CronTrigger(hour=REMINDER_HOUR_ROME, minute=0, timezone=ROME_TZ),
            id="expiry_reminders",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        self._scheduler.start()
        logger.info(
            "[SubscriptionScheduler] Avviato: changes ogni %d min, reminders alle %02d:00 %s",
            CHANGE_DETECTION_INTERVAL_MINUTES, REMINDER_HOUR_ROME, ROME_TZ.key,
        )

    def shutdown(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            logger.info("[SubscriptionScheduler] Fermato.")

    # --- Job runners ---

    async def _job_subscription_changes(self) -> None:
        db = SessionLocal()
        try:
            service = SubscriptionService(db)
            sent = service.process_subscription_changes()
            if sent > 0:
                logger.info("[SubscriptionScheduler] Cambi abbonamento: %d email inviate", sent)
        except Exception:
            logger.exception("[SubscriptionScheduler] Errore nel job cambi abbonamento")
        finally:
            db.close()

    async def _job_expiry_reminders(self) -> None:
        db = SessionLocal()
        try:
            service = SubscriptionService(db)
            sent = service.process_expiry_reminders()
            logger.info("[SubscriptionScheduler] Promemoria scadenza: %d email inviate", sent)
        except Exception:
            logger.exception("[SubscriptionScheduler] Errore nel job promemoria scadenza")
        finally:
            db.close()
