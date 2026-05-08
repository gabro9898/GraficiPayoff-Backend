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


def welcome_email(first_name: str) -> tuple[str, str, str]:
    """Email di benvenuto inviata al momento della registrazione."""
    safe_name = escape(first_name)

    subject = "Benvenuto in OptionTracker"

    html = f"""\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Benvenuto in OptionTracker</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 32px 24px;">
  <h1 style="font-size: 22px; margin-bottom: 16px;">Ciao {safe_name},</h1>
  <p>Benvenuto in <strong>OptionTracker</strong>.</p>
  <p>Il tuo account è stato creato. Da adesso puoi accedere all'app, costruire i
     tuoi grafici di payoff, monitorare il tuo portafoglio opzioni e analizzare
     il GEX dei principali sottostanti.</p>
  <p>Se hai domande, dubbi, o trovi qualcosa che non funziona, rispondi
     direttamente a questa email: arriva sulla mia casella personale e ti
     risponderò io.</p>
  <p>Buon trading,<br>Gabriele — OptionTracker</p>
</body>
</html>
"""

    text = (
        f"Ciao {first_name},\n\n"
        "Benvenuto in OptionTracker.\n\n"
        "Il tuo account è stato creato. Da adesso puoi accedere all'app, "
        "costruire i tuoi grafici di payoff, monitorare il tuo portafoglio "
        "opzioni e analizzare il GEX dei principali sottostanti.\n\n"
        "Se hai domande, dubbi, o trovi qualcosa che non funziona, rispondi "
        "direttamente a questa email: arriva sulla mia casella personale e ti "
        "risponderò io.\n\n"
        "Buon trading,\nGabriele — OptionTracker\n"
    )

    return subject, html, text


def password_reset_email(first_name: str, code: str, expires_in_minutes: int) -> tuple[str, str, str]:
    """Email contenente il codice OTP per reimpostare la password."""
    safe_name = escape(first_name)
    safe_code = escape(code)

    subject = "Reimposta la tua password OptionTracker"

    html = f"""\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Reimposta password OptionTracker</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; line-height: 1.6; max-width: 560px; margin: 0 auto; padding: 32px 24px;">
  <h1 style="font-size: 22px; margin-bottom: 16px;">Ciao {safe_name},</h1>
  <p>Hai richiesto di reimpostare la password del tuo account OptionTracker.</p>
  <p>Inserisci questo codice nell'app per scegliere una nuova password:</p>
  <div style="font-size: 32px; font-weight: bold; letter-spacing: 8px; text-align: center; padding: 24px; margin: 24px 0; background: #f4f4f6; border-radius: 8px; font-family: 'Courier New', monospace;">
    {safe_code}
  </div>
  <p style="color: #666; font-size: 14px;">Il codice scade tra <strong>{expires_in_minutes} minuti</strong>.</p>
  <p style="color: #666; font-size: 14px;">Se non hai richiesto tu il reset, puoi ignorare questa email: la tua password attuale resta valida.</p>
  <p>— OptionTracker</p>
</body>
</html>
"""

    text = (
        f"Ciao {first_name},\n\n"
        "Hai richiesto di reimpostare la password del tuo account OptionTracker.\n\n"
        f"Codice: {code}\n\n"
        f"Inseriscilo nell'app entro {expires_in_minutes} minuti per scegliere una nuova password.\n\n"
        "Se non hai richiesto tu il reset, ignora questa email: la tua password attuale resta valida.\n\n"
        "— OptionTracker\n"
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

    subject = "Pagamento ricevuto — il tuo abbonamento OptionTracker è attivo"

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
  <p>Il tuo abbonamento OptionTracker è attivo fino al <strong>{expiry_str}</strong>.</p>
  <p>Da adesso puoi accedere a tutte le funzionalità dell'app senza limitazioni.</p>
  <p style="margin-top: 28px;">Buon trading,<br>— OptionTracker</p>
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
        f"Il tuo abbonamento OptionTracker è attivo fino al {expiry_str}.\n\n"
        "Da adesso puoi accedere a tutte le funzionalità dell'app senza limitazioni.\n\n"
        "Buon trading,\n— OptionTracker\n\n"
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
        subject = "Ultimo giorno: il tuo abbonamento OptionTracker scade domani"
        urgency_intro = (
            "Ti scriviamo perché il tuo abbonamento OptionTracker scade <strong>domani</strong>. "
            "Per non perdere l'accesso all'app, rinnova oggi."
        )
        cta_label = "Rinnova ora"
        urgency_intro_text = (
            "Ti scriviamo perché il tuo abbonamento OptionTracker scade DOMANI. "
            "Per non perdere l'accesso all'app, rinnova oggi."
        )
    elif days_remaining == 2:
        subject = "Mancano 2 giorni alla scadenza del tuo abbonamento OptionTracker"
        urgency_intro = (
            "Il tuo abbonamento OptionTracker scade <strong>tra 2 giorni</strong> "
            f"(il {expiry_str})."
        )
        cta_label = "Rinnova ora"
        urgency_intro_text = (
            f"Il tuo abbonamento OptionTracker scade tra 2 giorni (il {expiry_str})."
        )
    elif days_remaining == 3:
        subject = "Mancano 3 giorni alla scadenza del tuo abbonamento OptionTracker"
        urgency_intro = (
            "Il tuo abbonamento OptionTracker scade <strong>tra 3 giorni</strong> "
            f"(il {expiry_str}). Ti consigliamo di rinnovarlo per non interrompere l'accesso."
        )
        cta_label = "Rinnova ora"
        urgency_intro_text = (
            f"Il tuo abbonamento OptionTracker scade tra 3 giorni (il {expiry_str}). "
            "Ti consigliamo di rinnovarlo per non interrompere l'accesso."
        )
    else:  # 7 giorni (o altri valori, fallback)
        subject = "Manca una settimana alla scadenza del tuo abbonamento OptionTracker"
        urgency_intro = (
            f"Il tuo abbonamento OptionTracker scade <strong>tra {days_remaining} giorni</strong>, "
            f"il {expiry_str}. Volevamo avvisarti per tempo, così puoi rinnovarlo con calma."
        )
        cta_label = "Rinnova abbonamento"
        urgency_intro_text = (
            f"Il tuo abbonamento OptionTracker scade tra {days_remaining} giorni, il {expiry_str}. "
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
  <p style="margin-top: 28px;">— OptionTracker</p>
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
        "— OptionTracker\n"
    )

    return subject, html, text
