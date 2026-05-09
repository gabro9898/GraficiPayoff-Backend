# ============================================================
# ★ BACKEND — FILE NUOVO
# Percorso: app/services/email_service.py
#
# Client Brevo per email transazionali.
# Punto di contatto unico con l'API esterna: chi vuole inviare
# email chiama send_transactional_email(...) e basta.
#
# Errori loggati ma mai sollevati: un fail di Brevo non deve
# rompere il flusso applicativo (registrazione, ecc.).
# ============================================================

import base64
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def send_transactional_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_content: str,
    text_content: str,
    reply_to_email: str | None = None,
    reply_to_name: str | None = None,
    attachments: list[dict] | None = None,
) -> None:
    """Invia un'email tramite Brevo. Fire-and-forget: errori loggati, mai sollevati.

    Se reply_to_email è passato, sovrascrive il default (BREVO_REPLY_TO).
    Utile per la chat di contatto: l'email arriva al founder con Reply-To
    dell'utente, così "Rispondi" va dritto all'utente.

    `attachments` accetta una lista di dict del tipo:
        {"filename": "screenshot.png", "content": <bytes>}
    Il content (bytes) viene encodato in base64 prima di passarlo a Brevo.
    """
    settings = get_settings()

    if not settings.BREVO_API_KEY:
        logger.warning("BREVO_API_KEY non configurata: email a %s non inviata", to_email)
        return

    reply_to: dict = {"email": reply_to_email or settings.BREVO_REPLY_TO}
    if reply_to_name:
        reply_to["name"] = reply_to_name

    payload: dict = {
        "sender": {
            "email": settings.BREVO_SENDER_EMAIL,
            "name": settings.BREVO_SENDER_NAME,
        },
        "to": [{"email": to_email, "name": to_name}],
        "replyTo": reply_to,
        "subject": subject,
        "htmlContent": html_content,
        "textContent": text_content,
    }

    if attachments:
        payload["attachment"] = [
            {
                "name": a["filename"],
                "content": base64.b64encode(a["content"]).decode("ascii"),
            }
            for a in attachments
        ]
    headers = {
        "api-key": settings.BREVO_API_KEY,
        "accept": "application/json",
        "content-type": "application/json",
    }

    try:
        response = httpx.post(BREVO_ENDPOINT, json=payload, headers=headers, timeout=10.0)
        response.raise_for_status()
        logger.info("Email '%s' inviata a %s (messageId=%s)",
                    subject, to_email, response.json().get("messageId"))
    except httpx.HTTPStatusError as exc:
        logger.error("Brevo ha rifiutato l'email a %s: %s — %s",
                     to_email, exc.response.status_code, exc.response.text)
    except httpx.HTTPError as exc:
        logger.error("Errore di rete inviando email a %s: %s", to_email, exc)
    except Exception as exc:
        logger.exception("Errore inatteso inviando email a %s: %s", to_email, exc)
