from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.services.stripe_service import StripeService
from app.schemas.stripe import CheckoutSessionRequest, CheckoutSessionResponse

router = APIRouter(prefix="/stripe", tags=["Stripe"])


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
def create_checkout_session(
    data: CheckoutSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = StripeService(db)
    try:
        url = service.create_checkout_session(current_user, data.price_id)
        return CheckoutSessionResponse(url=url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore Stripe: {str(e)}")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    service = StripeService(db)
    try:
        result = service.handle_webhook(payload, sig_header)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))