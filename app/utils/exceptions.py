from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base application exception."""
    pass


# --- Auth exceptions ---

class InvalidCredentialsException(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )


class InvalidTokenException(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


class EmailAlreadyExistsException(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )


class InvalidResetCodeException(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code",
        )


class EmailNotVerifiedException(AppException):
    """Sollevata in login quando l'utente esiste ma non ha ancora verificato
    l'email. Status 403 con detail dedicato così il frontend può intercettarlo
    e mostrare il bottone "reinvia codice di verifica".
    """
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Check your inbox to confirm your address.",
        )


class InvalidVerificationTokenException(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )


class VerificationRateLimitException(AppException):
    """Sollevata quando il resend-verification viene richiesto troppo presto.
    Il frontend deve mostrare un messaggio "riprova tra X secondi".
    """
    def __init__(self, retry_after_seconds: int):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {retry_after_seconds} seconds before requesting another verification email.",
            headers={"Retry-After": str(retry_after_seconds)},
        )


# --- Resource exceptions ---

class NotFoundException(AppException):
    def __init__(self, resource: str = "Resource"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found",
        )


class ForbiddenException(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this resource",
        )


class SubscriptionExpiredException(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your subscription has expired",
        )
