from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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
from services.rag_service import create_rag_service, enhance_chat_with_rag
from services.vision_service import VisionService

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
rag_service = create_rag_service()
vision_service = VisionService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Open Chat application...")
    
    # Initialize conversation storage
    await conversation_service.initialize()
    
    # Initialize RAG service
    await rag_service.initialize()
    
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
    """Get available Ollama models with vision capabilities info"""
    try:
        models = await ollama_service.get_available_models()
        vision_models = await vision_service.get_available_vision_models()
        
        # Add vision capability info to each model
        models_with_vision = []
        for model in models:
            models_with_vision.append({
                "name": model,
                "supports_vision": model in vision_models
            })
        
        return {
            "models": models,
            "models_with_info": models_with_vision,
            "vision_models": vision_models
        }
    except Exception as e:
        logger.error(f"Failed to fetch models: {e}")
        return {
            "models": [config.OLLAMA_MODEL],
            "models_with_info": [{"name": config.OLLAMA_MODEL, "supports_vision": False}],
            "vision_models": []
        }

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
        # Enhance query with RAG context if available
        enhanced_query = await enhance_chat_with_rag(request.message, rag_service)
        
        # Get response from Ollama
        model = request.model or config.OLLAMA_MODEL
        response_text = await ollama_service.generate_response(enhanced_query, model)
        
        # Save user message (original, not enhanced)
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

@app.post("/chat-vision", response_model=ChatResponse)
async def chat_with_vision(
    message: str = Form(...),
    model: str = Form(None),
    voice_id: str = Form(None),
    image: UploadFile = File(None)
):
    """Process chat message with optional image and return response"""
    try:
        # Determine model to use
        selected_model = model or config.OLLAMA_MODEL
        
        # Check if image is provided and model supports vision
        if image:
            # Validate image
            image_data = await image.read()
            if not vision_service.validate_image(image_data):
                raise HTTPException(status_code=400, detail="Invalid image format")
            
            # Check if model supports vision
            if not await vision_service.is_vision_model(selected_model):
                # Try to find a vision model
                vision_models = await vision_service.get_available_vision_models()
                if vision_models:
                    selected_model = vision_models[0]  # Use first available vision model
                    logger.info(f"Switched to vision model: {selected_model}")
                else:
                    raise HTTPException(status_code=400, detail="No vision models available for image analysis")
            
            # Get conversation context for better responses
            recent_messages = await conversation_service.get_recent_messages(5)
            context = [{"role": msg["role"], "content": msg["content"]} for msg in recent_messages]
            
            # Analyze image with vision model
            response_text = await vision_service.chat_with_image(
                message, image_data, selected_model, context
            )
            
            # Save image to temp directory for display
            image_filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image.filename}"
            image_path = os.path.join(config.AUDIO_TEMP_DIR, image_filename)
            with open(image_path, "wb") as f:
                f.write(image_data)
            
            # Save user message with image reference
            user_msg = ChatMessage(
                role="user",
                content=f"{message} [Image: {image_filename}]",
                timestamp=datetime.now()
            )
            
        else:
            # Regular text chat without image
            enhanced_query = await enhance_chat_with_rag(message, rag_service)
            response_text = await ollama_service.generate_response(enhanced_query, selected_model)
            
            # Save user message
            user_msg = ChatMessage(
                role="user",
                content=message,
                timestamp=datetime.now()
            )
        
        await conversation_service.save_message(user_msg)
        
        # Generate TTS audio for the response
        audio_file = None
        try:
            audio_file = await tts_service.generate_speech(response_text, voice_id)
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
            model=selected_model,
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

@app.delete("/conversations")
async def clear_conversations():
    """Clear all conversation history"""
    try:
        success = await conversation_service.clear_conversation()
        if success:
            return {"message": "Conversation history cleared successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear conversation history")
    except Exception as e:
        logger.error(f"Error clearing conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversations/stats")
async def get_conversation_stats():
    """Get conversation statistics"""
    try:
        messages = await conversation_service.get_recent_messages(limit=1000)  # Get more for stats
        total_messages = len(messages)
        user_messages = len([m for m in messages if m["role"] == "user"])
        assistant_messages = len([m for m in messages if m["role"] == "assistant"])
        
        # Get oldest and newest timestamps
        if messages:
            oldest = min(messages, key=lambda x: x["timestamp"])["timestamp"]
            newest = max(messages, key=lambda x: x["timestamp"])["timestamp"]
        else:
            oldest = newest = None
        
        return {
            "total_messages": total_messages,
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "oldest_message": oldest,
            "newest_message": newest
        }
    except Exception as e:
        logger.error(f"Error getting conversation stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# RAG Endpoints
@app.post("/rag/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and process a document for RAG"""
    temp_file_path = None
    try:
        if not rag_service.is_enabled():
            raise HTTPException(status_code=503, detail="RAG service is not available")
        
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")
        
        # Check file format
        supported_formats = rag_service.get_supported_formats()
        file_extension = f".{file.filename.split('.')[-1].lower()}"
        
        if file_extension not in supported_formats:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file format. Supported: {', '.join(supported_formats)}"
            )
        
        # Save uploaded file temporarily
        temp_dir = "temp_documents"
        os.makedirs(temp_dir, exist_ok=True)
        temp_file_path = os.path.join(temp_dir, file.filename)
        
        with open(temp_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Process document
        success = await rag_service.add_document(
            temp_file_path, 
            metadata={
                "filename": file.filename,
                "content_type": file.content_type,
                "upload_time": datetime.now().isoformat()
            }
        )
        
        # Clean up temp file
        os.remove(temp_file_path)
        
        if success:
            return {"message": f"Document '{file.filename}' processed successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to process document")
            
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/rag/stats")
async def get_rag_stats():
    """Get RAG system statistics"""
    try:
        return rag_service.get_stats()
    except Exception as e:
        logger.error(f"Error getting RAG stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/rag/search")
async def search_documents(query: str, max_results: int = 5):
    """Search documents in RAG system"""
    try:
        if not rag_service.is_enabled():
            raise HTTPException(status_code=503, detail="RAG service is not available")
        
        results = await rag_service.search_documents(query, max_results)
        return {"query": query, "results": results}
        
    except Exception as e:
        logger.error(f"Document search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/rag/documents")
async def list_rag_documents():
    """List all documents in RAG system"""
    try:
        documents = await rag_service.list_documents()
        return {"documents": documents}
    except Exception as e:
        logger.error(f"Error listing RAG documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/images/{filename}")
async def serve_image(filename: str):
    """Serve uploaded images"""
    try:
        image_path = os.path.join(config.AUDIO_TEMP_DIR, filename)
        if os.path.exists(image_path):
            return FileResponse(image_path)
        else:
            raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
        logger.error(f"Error serving image: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )