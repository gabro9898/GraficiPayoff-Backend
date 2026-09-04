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


# --- Broker / servizi esterni ---

class TastyTradeApiException(AppException):
    """TastyTrade ha risposto con un errore alla nostra chiamata.

    Serve a portare fino al client il MOTIVO vero del rifiuto (buying power
    insufficiente, simbolo inesistente, prezzo fuori tick). Prima al suo posto
    c'era una `Exception` nuda: FastAPI la trasformava in un 500 generato dal
    ServerErrorMiddleware, che sta FUORI dal CORS middleware — quindi la
    risposta arrivava al browser senza header CORS e in testo semplice, e il
    frontend non vedeva nemmeno un 500, ma un errore di rete con `response`
    indefinita. Il messaggio di TastyTrade spariva per strada.

    Lo status di TastyTrade NON viene propagato alla lettera:

      * 401 → il frontend ha un interceptor globale che lo legge come "sessione
        dell'app scaduta": rinnova il JWT, RIESEGUE la richiesta (su un ordine
        significherebbe inviarlo due volte) e, se il rinnovo fallisce, cancella
        i token buttando l'utente fuori dall'applicazione.
      * 403 → su GET /tastytrade/accounts il frontend lo interpreta come
        "grant TastyTrade revocato" e riapre da solo la popup OAuth: un 403 di
        permessi diventerebbe un giro di ri-autorizzazioni che non risolve.

    Tutto ciò che non è un errore di richiesta "pulito" diventa quindi 502 Bad
    Gateway — che è anche la verità tecnica: un servizio a monte ha risposto
    male. 502 è già la scelta del progetto per questi casi (app_info.py).
    """

    # Status che descrivono un problema della RICHIESTA e che il frontend può
    # ricevere senza effetti collaterali (verificato punto per punto sui
    # chiamanti). Tutti gli altri vengono rimappati su 502.
    STATUS_PROPAGABILI = frozenset({400, 404, 409, 422})

    def __init__(self, upstream_status: int, detail: str):
        super().__init__(
            status_code=(
                upstream_status
                if upstream_status in self.STATUS_PROPAGABILI
                else status.HTTP_502_BAD_GATEWAY
            ),
            detail=detail,
        )
        # Lo status originale resta leggibile per i log, anche quando quello
        # HTTP esposto è stato rimappato a 502.
        self.upstream_status = upstream_status
