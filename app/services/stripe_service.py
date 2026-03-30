# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/services/stripe_service.py
# ============================================================

import stripe
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.config import get_settings

settings = get_settings()

stripe.api_key = settings.STRIPE_SECRET_KEY

PRICE_MAP = {
    "monthly": settings.STRIPE_PRICE_MONTHLY,
    "annual": settings.STRIPE_PRICE_ANNUAL,
}

DURATION_MAP = {
    "monthly": timedelta(days=30),
    "annual": timedelta(days=365),
}


class StripeService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)

    def create_checkout_session(self, user: User, price_id: str) -> str:
        if price_id not in PRICE_MAP:
            raise ValueError(f"Piano non valido: {price_id}")

        session = stripe.checkout.Session.create(
            customer_email=user.email,
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{
                "price": PRICE_MAP[price_id],
                "quantity": 1,
            }],
            success_url=f"{settings.FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.FRONTEND_URL}/cancel",
            metadata={
                "user_id": user.id,
                "plan": price_id,
            },
        )

        return session.url

    def handle_webhook(self, payload: bytes, sig_header: str) -> dict:
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError:
            raise ValueError("Payload non valido")
        except stripe.error.SignatureVerificationError:
            raise ValueError("Firma webhook non valida")

        if event["type"] == "checkout.session.completed":
            self._handle_checkout_completed(event["data"]["object"])

        return {"status": "ok"}

    def _handle_checkout_completed(self, session: dict):
        user_id = session.get("metadata", {}).get("user_id")
        plan = session.get("metadata", {}).get("plan", "monthly")

        if not user_id:
            print("[Stripe] Webhook: user_id mancante nei metadata")
            return

        user = self.user_repo.find_by_id(user_id)
        if not user:
            print(f"[Stripe] Webhook: utente {user_id} non trovato")
            return

        duration = DURATION_MAP.get(plan, timedelta(days=30))
        now = datetime.now(timezone.utc)

        if user.subscription_expiry and user.subscription_expiry > now:
            new_expiry = user.subscription_expiry + duration
        else:
            new_expiry = now + duration

        self.user_repo.update(user, {"subscription_expiry": new_expiry})

        print(f"[Stripe] Abbonamento aggiornato: user={user.email}, piano={plan}, scadenza={new_expiry.isoformat()}")