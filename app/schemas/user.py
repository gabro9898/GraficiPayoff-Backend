from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# --- Request schemas ---

class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    # Consenso marketing GDPR — opzionale, default off. Il frontend deve
    # mostrare una checkbox separata, non pre-spuntata, non obbligatoria.
    marketing_consent: bool = False


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserUpdateRequest(BaseModel):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    subscription_expiry: datetime | None = None


# --- Response schemas ---

class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    is_active: bool
    email_verified: bool
    marketing_consent: bool
    subscription_expiry: datetime | None
    is_subscription_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# --- Password reset schemas ---

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=128)


# --- Email verification schemas ---

class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=255)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class RegisterResponse(BaseModel):
    """Risposta dell'endpoint /register: NON include token di accesso.
    L'utente deve verificare l'email prima di poter loggare.
    """
    id: str
    email: str
    email_verified: bool
    message: str = "Account created. Please check your inbox to verify your email."

    model_config = {"from_attributes": True}
