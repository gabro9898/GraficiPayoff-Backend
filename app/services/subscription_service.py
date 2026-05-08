# ============================================================
# ★ BACKEND — FILE NUOVO
# Percorso: app/services/subscription_service.py
#
# Logica dei due job dello scheduler abbonamenti:
#
# 1) process_subscription_changes()
#    - Confronta users.subscription_expiry vs users.last_processed_expiry
#    - Se è cambiato e la nuova è > vecchia (rinnovo/primo pagamento)
#      manda email "pagamento ricevuto"
#    - Sincronizza last_processed_expiry così non si rispedisce
#    - Funziona sia per pagamenti via Stripe che per modifiche manuali al DB
#
# 2) process_expiry_reminders()
#    - Scansiona gli utenti con abbonamento attivo
#    - Per i giorni rimanenti in {7, 3, 2, 1}, manda email se non già spedita
#      per quella scadenza
#    - Idempotente: la subscription_reminder_log evita doppi invii
# ============================================================

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User
from app.repositories.subscription_reminder_repository import SubscriptionReminderRepository
from app.services.email_service import send_transactional_email
from app.services.email_templates import (
    payment_confirmed_email,
    subscription_expiring_email,
)

logger = logging.getLogger(__name__)


# Giorni di anticipo per cui mandiamo un promemoria di scadenza.
REMINDER_DAYS = (7, 3, 2, 1)


class SubscriptionService:
    def __init__(self, db: Session):
        self.db = db
        self.reminder_repo = SubscriptionReminderRepository(db)
        self.settings = get_settings()

    # --- Job 1 ---

    def process_subscription_changes(self) -> int:
        """Rileva variazioni di subscription_expiry e manda l'email di conferma
        pagamento quando è un rinnovo o primo acquisto.
        Ritorna il numero di email inviate."""
        now = datetime.now(timezone.utc)
        sent = 0

        # Prendiamo tutti gli utenti dove i due valori divergono
        # (incluso il caso in cui uno dei due è NULL).
        candidates = (
            self.db.query(User)
            .filter(User.subscription_expiry.is_distinct_from(User.last_processed_expiry))
            .all()
        )

        for user in candidates:
            try:
                if self._handle_subscription_change(user, now):
                    sent += 1
                # In ogni caso, sincronizziamo last_processed_expiry così non
                # ritocchiamo lo stesso utente al prossimo giro.
                user.last_processed_expiry = user.subscription_expiry
                self.db.commit()
            except Exception:
                logger.exception(
                    "Errore processando cambio abbonamento per user_id=%s", user.id
                )
                self.db.rollback()

        return sent

    def _handle_subscription_change(self, user: User, now: datetime) -> bool:
        """Decide se per questo utente serve mandare l'email di conferma
        pagamento. Ritorna True se l'email è stata mandata."""
        new_expiry = user.subscription_expiry
        old_expiry = user.last_processed_expiry

        # Se la scadenza è stata rimossa (None), niente email
        if new_expiry is None:
            return False

        # Se la nuova scadenza è nel passato, niente email (è un dato di
        # un abbonamento già scaduto, non un pagamento)
        if new_expiry <= now:
            return False

        # Solo se il valore è "salito" (rinnovo / primo pagamento).
        # Una riduzione manuale della scadenza non manda email.
        if old_expiry is not None and new_expiry <= old_expiry:
            return False

        subject, html, text = payment_confirmed_email(
            first_name=user.first_name,
            expiry_date=new_expiry,
            renewal_url=self.settings.SUBSCRIPTION_RENEWAL_URL,
        )
        send_transactional_email(
            to_email=user.email,
            to_name=f"{user.first_name} {user.last_name}",
            subject=subject,
            html_content=html,
            text_content=text,
        )
        logger.info(
            "Email pagamento confermato inviata a %s (scadenza=%s)",
            user.email, new_expiry.isoformat()
        )
        return True

    # --- Job 2 ---

    def process_expiry_reminders(self) -> int:
        """Scansiona gli utenti con abbonamento attivo e spedisce i promemoria
        7/3/2/1 giorni prima della scadenza, una sola volta per ciclo."""
        now = datetime.now(timezone.utc)
        sent = 0

        active_users = (
            self.db.query(User)
            .filter(User.subscription_expiry.is_not(None))
            .filter(User.subscription_expiry > now)
            .all()
        )

        for user in active_users:
            days_left = (user.subscription_expiry.date() - now.date()).days
            if days_left not in REMINDER_DAYS:
                continue

            try:
                if self.reminder_repo.has_been_sent(
                    user.id, user.subscription_expiry, days_left
                ):
                    continue

                subject, html, text = subscription_expiring_email(
                    first_name=user.first_name,
                    days_remaining=days_left,
                    expiry_date=user.subscription_expiry,
                    renewal_url=self.settings.SUBSCRIPTION_RENEWAL_URL,
                )
                send_transactional_email(
                    to_email=user.email,
                    to_name=f"{user.first_name} {user.last_name}",
                    subject=subject,
                    html_content=html,
                    text_content=text,
                )
                # Salviamo il log SOLO dopo aver chiamato l'invio, così se Brevo
                # solleva un errore (gestito dentro send_transactional_email,
                # quindi loggato e ingoiato) non scriviamo comunque il log.
                # Nota: send_transactional_email NON solleva eccezioni, quindi
                # il log viene scritto anche se Brevo ha rifiutato. Trade-off
                # accettabile: meglio "non rispedire" che "rispedire all'infinito".
                self.reminder_repo.record_sent(
                    user.id, user.subscription_expiry, days_left
                )
                sent += 1
                logger.info(
                    "Promemoria scadenza %dgg inviato a %s (scadenza=%s)",
                    days_left, user.email, user.subscription_expiry.isoformat()
                )
            except Exception:
                logger.exception(
                    "Errore processando promemoria scadenza per user_id=%s", user.id
                )

        return sent
