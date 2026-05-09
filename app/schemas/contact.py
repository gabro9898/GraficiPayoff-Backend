from pydantic import BaseModel, Field


class ContactMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ContactMessageResponse(BaseModel):
    message: str
