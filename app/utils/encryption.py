# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/utils/encryption.py
# Crittografia simmetrica Fernet per token OAuth
# ============================================================

from cryptography.fernet import Fernet, InvalidToken
from app.config import get_settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = get_settings().TOKEN_ENCRYPTION_KEY
        if not key:
            # Se non configurata, genera una key temporanea (NON adatto a produzione!)
            import warnings
            warnings.warn("TOKEN_ENCRYPTION_KEY not set — using ephemeral key. Tokens won't survive restart!")
            key = Fernet.generate_key().decode()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_token(plaintext: str) -> str:
    """Cripta un token e ritorna il ciphertext base64."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str | None:
    """Decripta un token. Ritorna None se decryption fallisce."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return None