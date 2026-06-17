"""Configurazione del rate limiter (slowapi) condivisa fra main.py e i router.

Audit 2026-05-23: aggiunto per limitare il brute-force sugli endpoint di
autenticazione (/auth/login, /auth/register, /auth/forgot-password,
/auth/resend-verification). Il limiter vive in un modulo dedicato per
evitare circular import con auth.py (che applica i decoratori).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Limiter di default basato sull'IP del client.
# Note operative:
# - dietro a un reverse proxy (Render usa Cloudflare/proxy), assicurarsi che
#   X-Forwarded-For sia rispettato. slowapi.util.get_remote_address gestisce
#   il fallback ma su Render conviene verificarlo nei log la prima volta.
# - per limiti differenti (es. per-utente loggato) si possono passare
#   `key_func` custom direttamente nel decoratore @limiter.limit(...).
limiter = Limiter(key_func=get_remote_address)
