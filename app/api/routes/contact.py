from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.controllers.contact_controller import ContactController
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.schemas.contact import ContactMessageResponse

router = APIRouter(prefix="/contact", tags=["Contact"])

# ── Limiti allegati ──
MAX_ATTACHMENTS = 5
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024          # 5 MB per file
MAX_TOTAL_SIZE_BYTES = 10 * 1024 * 1024        # 10 MB totali per messaggio
MAX_MESSAGE_LENGTH = 4000

# Estensioni vietate per sicurezza (file eseguibili / script).
# Tutto il resto è accettato — Brevo gestirà il MIME type lato suo.
FORBIDDEN_EXTENSIONS = {
    "exe", "bat", "cmd", "sh", "ps1", "psm1", "vbs", "scr",
    "msi", "com", "dll", "jar", "app", "deb", "rpm", "apk",
}


def _file_extension(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


@router.post("/send", response_model=ContactMessageResponse, status_code=200)
async def send_contact_message(
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
):
    """Riceve un messaggio (con eventuali allegati) dalla chat di contatto e lo
    spedisce via email al founder. Auth richiesta — solo utenti loggati.
    L'invio è in background: non blocca la risposta.
    """
    # ── Validazione messaggio ──
    msg = (message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Il messaggio non può essere vuoto.")
    if len(msg) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Il messaggio è troppo lungo (max {MAX_MESSAGE_LENGTH} caratteri).",
        )

    # ── Validazione allegati ──
    if len(files) > MAX_ATTACHMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Massimo {MAX_ATTACHMENTS} file per messaggio.",
        )

    attachments: list[dict] = []
    total_size = 0
    for f in files:
        ext = _file_extension(f.filename)
        if ext in FORBIDDEN_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo di file non consentito: '{f.filename}'.",
            )

        content = await f.read()
        size = len(content)
        if size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Il file '{f.filename}' supera i 5 MB.",
            )
        total_size += size
        if total_size > MAX_TOTAL_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail="Dimensione totale degli allegati troppo grande (max 10 MB).",
            )

        attachments.append({"filename": f.filename or "allegato", "content": content})

    # ── Invio in background ──
    controller = ContactController()
    background_tasks.add_task(
        controller.send_message,
        user=current_user,
        message=msg,
        attachments=attachments or None,
    )
    return ContactMessageResponse(
        message="Messaggio inviato. Ti risponderemo via email."
    )
