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
