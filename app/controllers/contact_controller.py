# ============================================================
# ★ BACKEND — FILE NUOVO
# Percorso: app/controllers/contact_controller.py
#
# Orchestrazione della chat di contatto: l'utente loggato manda un
# messaggio e noi lo recapitiamo via email al founder.
# Reply-To = email dell'utente, così "Rispondi" va dritto all'utente.
# ============================================================

from app.config import get_settings
from app.models.user import User
from app.services.email_service import send_transactional_email
from app.services.email_templates import contact_message_email


class ContactController:
    def __init__(self):
        self.settings = get_settings()

    def send_message(
        self,
        user: User,
        message: str,
        attachments: list[dict] | None = None,
    ) -> None:
        subject, html, text = contact_message_email(
            user_first_name=user.first_name,
            user_last_name=user.last_name,
            user_email=user.email,
            user_created_at=user.created_at,
            message=message,
        )
        send_transactional_email(
            to_email=self.settings.BREVO_REPLY_TO,
            to_name="Option Tracker — Founder",
            subject=subject,
            html_content=html,
            text_content=text,
            reply_to_email=user.email,
            reply_to_name=f"{user.first_name} {user.last_name}",
            attachments=attachments,
        )
