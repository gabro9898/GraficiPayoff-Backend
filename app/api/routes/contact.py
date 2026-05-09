from fastapi import APIRouter, BackgroundTasks, Depends

from app.controllers.contact_controller import ContactController
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.schemas.contact import ContactMessageRequest, ContactMessageResponse

router = APIRouter(prefix="/contact", tags=["Contact"])


@router.post("/send", response_model=ContactMessageResponse, status_code=200)
def send_contact_message(
    data: ContactMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Riceve un messaggio dalla chat di contatto sulla landing page e lo
    spedisce via email al founder. Auth richiesta — solo utenti loggati.
    L'invio è in background: non blocca la risposta.
    """
    controller = ContactController()
    background_tasks.add_task(
        controller.send_message,
        user=current_user,
        message=data.message,
    )
    return ContactMessageResponse(
        message="Messaggio inviato. Ti risponderemo via email."
    )
