from datetime import datetime

from pydantic import BaseModel


class ChatImageOut(BaseModel):
    path: str
    filename: str


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    images: list[ChatImageOut] = []
    status: str
    error_msg: str | None = None
    usage: dict = {}
    created_at: datetime


class ChatSessionListItem(BaseModel):
    id: str
    title: str
    last_message_at: datetime | None = None
    created_at: datetime


class ChatSessionListOut(BaseModel):
    sessions: list[ChatSessionListItem]


class ChatSessionOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    last_message_at: datetime | None = None
    messages: list[ChatMessageOut]


class ChatSessionCreated(BaseModel):
    session_id: str
