from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class ChatMessage(BaseModel):
    id: Optional[int] = None
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    audio_file: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    voice_id: Optional[str] = None
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9

class GeneratedImage(BaseModel):
    url: str
    prompt: str
    reason: str
    style: Optional[str] = "artistic"
    ai_initiated: bool = False

class ChatResponse(BaseModel):
    response: str
    model: str
    timestamp: datetime
    audio_file: Optional[str] = None
    generated_image: Optional[GeneratedImage] = None

class TranscriptionRequest(BaseModel):
    audio_data: bytes

class TranscriptionResponse(BaseModel):
    text: str

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None

class TTSResponse(BaseModel):
    audio_file: str

class HealthResponse(BaseModel):
    status: str
    ollama_connected: bool
    tts_provider: str
    services: List[str]