from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import logging
from datetime import datetime
import os
from contextlib import asynccontextmanager

from config import config
from models.schemas import *
from services.ollama_service import OllamaService
from services.stt_service import STTService
from services.tts_service import TTSService
from services.conversation_service import ConversationService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate configuration
config_errors = config.validate_config()
if config_errors:
    for error in config_errors:
        logger.error(f"Configuration error: {error}")
    if not config.DEBUG:
        raise RuntimeError("Configuration validation failed")

# Initialize services
ollama_service = OllamaService()
stt_service = STTService()
tts_service = TTSService()
conversation_service = ConversationService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Open Chat application...")
    
    # Initialize conversation storage
    await conversation_service.initialize()
    
    # Test Ollama connection
    if await ollama_service.health_check():
        logger.info("✅ Ollama connection successful")
    else:
        logger.warning("⚠️  Ollama connection failed - check if Ollama is running")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Open Chat application...")

app = FastAPI(
    title="Open Chat",
    description="Local voice and text chat with Ollama models",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="../frontend"), name="static")

@app.get("/")
async def serve_frontend():
    """Serve the main frontend page"""
    return FileResponse("../frontend/index.html")

@app.get("/voices")
async def get_voices():
    """Get available voices from current TTS provider"""
    try:
        if config.TTS_PROVIDER == "elevenlabs":
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
            voice_list = client.voices.get_all()
            voices = [
                {
                    "id": voice.voice_id,
                    "name": voice.name,
                    "category": voice.category
                }
                for voice in voice_list.voices
            ]
            return {"voices": voices}
        else:
            # For local TTS, return basic options
            return {"voices": [{"id": "default", "name": "Default Voice", "category": "local"}]}
    except Exception as e:
        logger.error(f"Failed to fetch voices: {e}")
        return {"voices": [{"id": "default", "name": "Default Voice", "category": "local"}]}

@app.get("/models")
async def get_models():
    """Get available Ollama models"""
    try:
        models = await ollama_service.get_available_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Failed to fetch models: {e}")
        return {"models": [config.OLLAMA_MODEL]}

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    ollama_connected = await ollama_service.health_check()
    
    services = ["stt", "conversation"]
    if config.TTS_PROVIDER == "elevenlabs" and config.ELEVENLABS_API_KEY:
        services.append("tts-elevenlabs")
    else:
        services.append("tts-local")
    
    return HealthResponse(
        status="healthy" if ollama_connected else "degraded",
        ollama_connected=ollama_connected,
        tts_provider=config.TTS_PROVIDER,
        services=services
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process chat message and return response"""
    try:
        # Get response from Ollama
        model = request.model or config.OLLAMA_MODEL
        response_text = await ollama_service.generate_response(request.message, model)
        
        # Save user message
        user_msg = ChatMessage(
            role="user",
            content=request.message,
            timestamp=datetime.now()
        )
        await conversation_service.save_message(user_msg)
        
        # Generate TTS audio for the response
        audio_file = None
        try:
            audio_file = await tts_service.generate_speech(response_text, request.voice_id)
        except Exception as e:
            logger.warning(f"TTS generation failed: {e}")
        
        # Save assistant message
        assistant_msg = ChatMessage(
            role="assistant",
            content=response_text,
            timestamp=datetime.now(),
            audio_file=audio_file
        )
        await conversation_service.save_message(assistant_msg)
        
        return ChatResponse(
            response=response_text,
            model=model,
            timestamp=datetime.now(),
            audio_file=audio_file
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(audio: UploadFile = File(...)):
    """Transcribe uploaded audio to text"""
    try:
        if not audio.content_type or not audio.content_type.startswith("audio/"):
            raise HTTPException(status_code=400, detail="Invalid audio file")
        
        # Check file size
        content = await audio.read()
        if len(content) > config.MAX_AUDIO_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Audio file too large")
        
        # Transcribe audio
        text = await stt_service.transcribe(content, audio.filename)
        
        return TranscriptionResponse(text=text)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/speak", response_model=TTSResponse)
async def generate_speech(request: TTSRequest):
    """Generate speech from text"""
    try:
        audio_file = await tts_service.generate_speech(
            request.text, 
            request.voice_id
        )
        
        return TTSResponse(audio_file=audio_file)
        
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve audio files"""
    file_path = os.path.join(config.AUDIO_TEMP_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        file_path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-cache"}
    )

@app.get("/conversations")
async def get_conversations():
    """Get conversation history"""
    try:
        messages = await conversation_service.get_recent_messages()
        return {"messages": messages}
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )