# ============================================================
# ★ BACKEND — FILE NUOVO
# Percorso: app/services/email_templates.py
#
# Template per email transazionali. Funzioni pure: ricevono i dati,
# ritornano (subject, html, text). Nessun side-effect, nessun I/O.
#
# Per ora una sola funzione: welcome_email().
# Quando i template diventeranno più complessi, si migrerà a file
# HTML separati con un motore di template.
# ============================================================

from datetime import datetime
from html import escape


def verification_email(
    first_name: str,
    verification_url: str,
    expires_in_hours: int,
) -> tuple[str, str, str]:
    """Email di benvenuto + conferma indirizzo email.
    Inviata al momento della registrazione (e al resend). Contiene il link
    cliccabile che porta alla pagina di conferma sul landing.
    """
    safe_name = escape(first_name)
    safe_url = escape(verification_url, quote=True)

    subject = "Conferma il tuo indirizzo email — Option Tracker"

    html = f"""\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Conferma email Option Tracker</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 32px 24px;">
  <h1 style="font-size: 22px; margin-bottom: 16px;">Ciao {safe_name},</h1>
  <p>Benvenuto in <strong>Option Tracker</strong>.</p>
  <p>Per completare la registrazione e attivare il tuo account, conferma il
     tuo indirizzo email cliccando il pulsante qui sotto:</p>
  <p style="text-align: center; margin: 28px 0;">
    <a href="{safe_url}" style="display: inline-block; background: #4f6ef7; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 600;">Conferma email</a>
  </p>
  <p style="color: #666; font-size: 14px;">
     Se il pulsante non funziona, copia e incolla questo link nel browser:<br>
     <a href="{safe_url}" style="color: #4f6ef7; word-break: break-all;">{safe_url}</a>
  </p>
  <p style="color: #666; font-size: 14px;">Il link scade tra <strong>{expires_in_hours} ore</strong>.</p>
  <p style="color: #666; font-size: 14px;">Se non hai creato tu questo account, ignora questa email.</p>
  <p>— Option Tracker</p>
</body>
</html>
"""

    text = (
        f"Ciao {first_name},\n\n"
        "Benvenuto in Option Tracker.\n\n"
        "Per completare la registrazione e attivare il tuo account, conferma il "
        "tuo indirizzo email aprendo questo link:\n\n"
        f"{verification_url}\n\n"
        f"Il link scade tra {expires_in_hours} ore.\n\n"
        "Se non hai creato tu questo account, ignora questa email.\n\n"
        "— Option Tracker\n"
    )

    return subject, html, text


def welcome_email(first_name: str) -> tuple[str, str, str]:
    """Email di benvenuto inviata al momento della registrazione."""
    safe_name = escape(first_name)

    subject = "Benvenuto in Option Tracker"

    html = f"""\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Benvenuto in Option Tracker</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 32px 24px;">
  <h1 style="font-size: 22px; margin-bottom: 16px;">Ciao {safe_name},</h1>
  <p>Benvenuto in <strong>Option Tracker</strong>.</p>
  <p>Il tuo account è stato creato. Da adesso puoi accedere all'app, costruire i
     tuoi grafici di payoff, monitorare il tuo portafoglio opzioni e analizzare
     il GEX dei principali sottostanti.</p>
  <p>Se hai domande, dubbi, o trovi qualcosa che non funziona, rispondi
     direttamente a questa email: arriva sulla mia casella personale e ti
     risponderò io.</p>
  <p>Buon trading,<br>Gabriele — Option Tracker</p>
</body>
</html>
"""

    text = (
        f"Ciao {first_name},\n\n"
        "Benvenuto in Option Tracker.\n\n"
        "Il tuo account è stato creato. Da adesso puoi accedere all'app, "
        "costruire i tuoi grafici di payoff, monitorare il tuo portafoglio "
        "opzioni e analizzare il GEX dei principali sottostanti.\n\n"
        "Se hai domande, dubbi, o trovi qualcosa che non funziona, rispondi "
        "direttamente a questa email: arriva sulla mia casella personale e ti "
        "risponderò io.\n\n"
        "Buon trading,\nGabriele — Option Tracker\n"
    )

    return subject, html, text


def password_reset_email(first_name: str, code: str, expires_in_minutes: int) -> tuple[str, str, str]:
    """Email contenente il codice OTP per reimpostare la password."""
    safe_name = escape(first_name)
    safe_code = escape(code)

    subject = "Reimposta la tua password Option Tracker"

    html = f"""\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Reimposta password Option Tracker</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 32px 24px;">
  <h1 style="font-size: 22px; margin-bottom: 16px;">Ciao {safe_name},</h1>
  <p>Hai richiesto di reimpostare la password del tuo account Option Tracker.</p>
  <p>Inserisci questo codice nell'app per scegliere una nuova password:</p>
  <div style="font-size: 32px; font-weight: bold; letter-spacing: 8px; text-align: center; padding: 24px; margin: 24px 0; background: #f4f4f6; border-radius: 8px; font-family: 'Courier New', monospace;">
    {safe_code}
  </div>
  <p style="color: #666; font-size: 14px;">Il codice scade tra <strong>{expires_in_minutes} minuti</strong>.</p>
  <p style="color: #666; font-size: 14px;">Se non hai richiesto tu il reset, puoi ignorare questa email: la tua password attuale resta valida.</p>
  <p>— Option Tracker</p>
</body>
</html>
"""

    text = (
        f"Ciao {first_name},\n\n"
        "Hai richiesto di reimpostare la password del tuo account Option Tracker.\n\n"
        f"Codice: {code}\n\n"
        f"Inseriscilo nell'app entro {expires_in_minutes} minuti per scegliere una nuova password.\n\n"
        "Se non hai richiesto tu il reset, ignora questa email: la tua password attuale resta valida.\n\n"
        "— Option Tracker\n"
    )

    return subject, html, text


def _format_italian_date(dt: datetime) -> str:
    """Formatta una data in italiano leggibile, es: '15 maggio 2026'."""
    months = [
        "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    ]
    return f"{dt.day} {months[dt.month - 1]} {dt.year}"


def payment_confirmed_email(
    first_name: str,
    expiry_date: datetime,
    renewal_url: str,
) -> tuple[str, str, str]:
    """Email inviata quando subscription_expiry viene aggiornato a una data
    futura (pagamento Stripe ricevuto o rinnovo manuale)."""
    safe_name = escape(first_name)
    expiry_str = _format_italian_date(expiry_date)
    safe_url = escape(renewal_url, quote=True)

    subject = "Pagamento ricevuto — il tuo abbonamento Option Tracker è attivo"

    html = f"""\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Pagamento ricevuto</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 32px 24px;">
  <h1 style="font-size: 22px; margin-bottom: 16px;">Ciao {safe_name},</h1>
  <p>Abbiamo ricevuto il tuo pagamento. Grazie!</p>
  <p>Il tuo abbonamento Option Tracker è attivo fino al <strong>{expiry_str}</strong>.</p>
  <p>Da adesso puoi accedere a tutte le funzionalità dell'app senza limitazioni.</p>
  <p style="margin-top: 28px;">Buon trading,<br>— Option Tracker</p>
  <hr style="border: none; border-top: 1px solid #e5e5e5; margin: 28px 0;">
  <p style="color: #888; font-size: 12px;">
    Hai domande sul tuo abbonamento? Rispondi direttamente a questa email.
    <br>Per gestire o rinnovare l'abbonamento: <a href="{safe_url}" style="color: #4f6ef7;">{safe_url}</a>
  </p>
</body>
</html>
"""

    text = (
        f"Ciao {first_name},\n\n"
        "Abbiamo ricevuto il tuo pagamento. Grazie!\n\n"
        f"Il tuo abbonamento Option Tracker è attivo fino al {expiry_str}.\n\n"
        "Da adesso puoi accedere a tutte le funzionalità dell'app senza limitazioni.\n\n"
        "Buon trading,\n— Option Tracker\n\n"
        f"Per gestire l'abbonamento: {renewal_url}\n"
    )

    return subject, html, text


def subscription_expiring_email(
    first_name: str,
    days_remaining: int,
    expiry_date: datetime,
    renewal_url: str,
) -> tuple[str, str, str]:
    """Email di promemoria a 7/3/2/1 giorni dalla scadenza dell'abbonamento.
    La copy si adatta in base ai giorni rimanenti (più urgente man mano)."""
    safe_name = escape(first_name)
    expiry_str = _format_italian_date(expiry_date)
    safe_url = escape(renewal_url, quote=True)

    if days_remaining == 1:
        subject = "Ultimo giorno: il tuo abbonamento Option Tracker scade domani"
        urgency_intro = (
            "Ti scriviamo perché il tuo abbonamento Option Tracker scade <strong>domani</strong>. "
            "Per non perdere l'accesso all'app, rinnova oggi."
        )
        cta_label = "Rinnova ora"
        urgency_intro_text = (
            "Ti scriviamo perché il tuo abbonamento Option Tracker scade DOMANI. "
            "Per non perdere l'accesso all'app, rinnova oggi."
        )
    elif days_remaining == 2:
        subject = "Mancano 2 giorni alla scadenza del tuo abbonamento Option Tracker"
        urgency_intro = (
            "Il tuo abbonamento Option Tracker scade <strong>tra 2 giorni</strong> "
            f"(il {expiry_str})."
        )
        cta_label = "Rinnova ora"
        urgency_intro_text = (
            f"Il tuo abbonamento Option Tracker scade tra 2 giorni (il {expiry_str})."
        )
    elif days_remaining == 3:
        subject = "Mancano 3 giorni alla scadenza del tuo abbonamento Option Tracker"
        urgency_intro = (
            "Il tuo abbonamento Option Tracker scade <strong>tra 3 giorni</strong> "
            f"(il {expiry_str}). Ti consigliamo di rinnovarlo per non interrompere l'accesso."
        )
        cta_label = "Rinnova ora"
        urgency_intro_text = (
            f"Il tuo abbonamento Option Tracker scade tra 3 giorni (il {expiry_str}). "
            "Ti consigliamo di rinnovarlo per non interrompere l'accesso."
        )
    else:  # 7 giorni (o altri valori, fallback)
        subject = "Manca una settimana alla scadenza del tuo abbonamento Option Tracker"
        urgency_intro = (
            f"Il tuo abbonamento Option Tracker scade <strong>tra {days_remaining} giorni</strong>, "
            f"il {expiry_str}. Volevamo avvisarti per tempo, così puoi rinnovarlo con calma."
        )
        cta_label = "Rinnova abbonamento"
        urgency_intro_text = (
            f"Il tuo abbonamento Option Tracker scade tra {days_remaining} giorni, il {expiry_str}. "
            "Volevamo avvisarti per tempo, così puoi rinnovarlo con calma."
        )

    html = f"""\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 32px 24px;">
  <h1 style="font-size: 22px; margin-bottom: 16px;">Ciao {safe_name},</h1>
  <p>{urgency_intro}</p>
  <p>Il rinnovo richiede meno di un minuto:</p>
  <p style="text-align: center; margin: 28px 0;">
    <a href="{safe_url}" style="display: inline-block; background: #4f6ef7; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600;">{cta_label}</a>
  </p>
  <p style="color: #666; font-size: 14px;">
    Se hai già rinnovato, ignora questa email: ricevuto il pagamento, la scadenza si aggiorna automaticamente.
  </p>
  <p style="margin-top: 28px;">— Option Tracker</p>
  <hr style="border: none; border-top: 1px solid #e5e5e5; margin: 28px 0;">
  <p style="color: #888; font-size: 12px;">
    Domande? Rispondi direttamente a questa email.
  </p>
</body>
</html>
"""

    text = (
        f"Ciao {first_name},\n\n"
        f"{urgency_intro_text}\n\n"
        f"Per rinnovare: {renewal_url}\n\n"
        "Se hai già rinnovato, ignora questa email: ricevuto il pagamento, "
        "la scadenza si aggiorna automaticamente.\n\n"
        "— Option Tracker\n"
    )

    return subject, html, text


def contact_message_email(
    user_first_name: str,
    user_last_name: str,
    user_email: str,
    user_created_at: datetime | None,
    message: str,
) -> tuple[str, str, str]:
    """Email che il founder riceve quando un utente loggato manda un messaggio
    dalla chat di contatto sulla landing page.
    Reply-To viene impostato sull'email dell'utente dal chiamante (email_service)
    così premendo "Rispondi" si risponde direttamente all'utente.
    """
    safe_first = escape(user_first_name)
    safe_last = escape(user_last_name)
    safe_email = escape(user_email)
    safe_message_html = escape(message).replace("\n", "<br>")
    registered_at = (
        user_created_at.strftime("%d/%m/%Y") if user_created_at else "—"
    )

    subject = f"Nuovo messaggio da {user_first_name} {user_last_name} ({user_email})"

    html = f"""\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6; max-width: 620px; margin: 0 auto; padding: 32px 24px;">
  <h1 style="font-size: 20px; margin: 0 0 8px;">Nuovo messaggio dalla chat Option Tracker</h1>
  <p style="color: #666; margin: 0 0 24px; font-size: 14px;">
    Per rispondere all'utente: premi semplicemente "Rispondi" — il messaggio andrà direttamente a {safe_email}.
  </p>

  <div style="background: #f6f7f9; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px 18px; margin-bottom: 18px;">
    <div style="font-size: 12px; text-transform: uppercase; color: #888; letter-spacing: 0.5px; margin-bottom: 6px;">Utente</div>
    <div style="font-size: 16px; font-weight: 600;">{safe_first} {safe_last}</div>
    <div style="font-size: 14px; margin-top: 4px;">
      <a href="mailto:{safe_email}" style="color: #4f6ef7; text-decoration: none;">{safe_email}</a>
    </div>
    <div style="font-size: 13px; color: #888; margin-top: 6px;">Registrato il {registered_at}</div>
  </div>

  <div style="background: #ffffff; border-left: 4px solid #4f6ef7; padding: 14px 18px;">
    <div style="font-size: 12px; text-transform: uppercase; color: #888; letter-spacing: 0.5px; margin-bottom: 6px;">Messaggio</div>
    <div style="font-size: 15px; white-space: pre-wrap;">{safe_message_html}</div>
  </div>

  <hr style="border: none; border-top: 1px solid #e5e5e5; margin: 28px 0;">
  <p style="color: #aaa; font-size: 12px; margin: 0;">
    Email generata automaticamente dalla chat di contatto Option Tracker.
  </p>
</body>
</html>
"""

    text = (
        f"Nuovo messaggio dalla chat Option Tracker\n\n"
        f"Da: {user_first_name} {user_last_name} <{user_email}>\n"
        f"Registrato il: {registered_at}\n\n"
        "Messaggio:\n"
        f"{message}\n\n"
        "---\n"
        f"Per rispondere, basta premere 'Rispondi' a questa email.\n"
    )

    return subject, html, text
