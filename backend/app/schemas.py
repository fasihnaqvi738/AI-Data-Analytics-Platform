from datetime import datetime
from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class FileResponse(BaseModel):
    id: int
    original_filename: str
    content_type: str | None
    size: int
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class FileUpdate(BaseModel):
    original_filename: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    file_id: int
    prompt: str
    history: list[ChatMessage] = []


class ChartResponse(BaseModel):
    title: str
    type: str
    labels: list[str]
    values: list[float]


class ChatResponse(BaseModel):
    answer: str
    charts: list[ChartResponse] = []


class ReportCreate(BaseModel):
    file_id: int | None = None
    messages: list[ChatMessage]


class ReportResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    source_file_id: int | None

    model_config = {"from_attributes": True}
