from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import logging
from datetime import datetime
import hashlib
import os
from contextlib import asynccontextmanager
from pathlib import Path

from config import config
from models.schemas import *
from services.ollama_service import OllamaService
from services.openai_service import OpenAIService
from services.archive_service import ArchiveService
from services.chatgpt_export_parser import parse_chatgpt_export_file
from services.research_vault_service import ResearchVaultService
from services.stt_service import STTService
from services.tts_service import TTSService
from services.conversation_service import ConversationService
from services.rag_service import create_rag_service, enhance_chat_with_rag
from services.vision_service import VisionService
from services.comfyui_service import ComfyUIService

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
openai_service = OpenAIService()
stt_service = STTService()
tts_service = TTSService()
conversation_service = ConversationService()
rag_service = create_rag_service()
archive_llm_service = None
if (
    config.ARCHIVE_ANALYSIS_PROVIDER == "openai"
    and config.MODEL_PROVIDER == "openai"
    and (not config.LAN_ONLY or config.is_lan_safe_url(config.OPENAI_BASE_URL))
):
    archive_llm_service = openai_service
elif config.ARCHIVE_ANALYSIS_PROVIDER == "local":
    archive_llm_service = ollama_service
archive_service = ArchiveService(rag_service.vector_store.db_path, analysis_service=archive_llm_service, rag_service=rag_service)
vision_service = VisionService()
comfyui_service = ComfyUIService()
research_vault_service = ResearchVaultService(rag_service.vector_store.db_path)


def get_default_chat_model() -> str:
    """Return the configured default chat model for the active provider."""
    if config.MODEL_PROVIDER == "openai":
        return config.OPENAI_MODEL
    return config.OLLAMA_MODEL


def get_active_chat_service():
    """Return the active chat service instance."""
    if config.MODEL_PROVIDER == "openai":
        return openai_service
    return ollama_service


def format_rag_sources(raw_sources):
    """Convert retrieved source dicts to API-safe response objects."""
    return [
        RAGSource(
            source_id=source["source_id"],
            filename=source["filename"],
            source=source["source"],
            chunk_index=source["chunk_index"],
            total_chunks=source["total_chunks"],
            similarity=source["similarity"],
            snippet=source["snippet"],
        )
        for source in raw_sources
    ]


def append_rag_citation_summary(response_text: str, rag_sources):
    """Ensure source references are visible even if the model omits them inline."""
    if not rag_sources:
        return response_text

    summary_lines = ["", "Sources:"]
    for source in rag_sources:
        summary_lines.append(
            f"[{source.source_id}] {source.filename} (chunk {source.chunk_index + 1}/{source.total_chunks})"
        )

    return f"{response_text.rstrip()}\n" + "\n".join(summary_lines)


def merge_prompt_contexts(user_query: str, personality_context: str, rag_query: str):
    """Combine background personality memory with exact retrieval context."""
    if personality_context and rag_query != user_query:
        return f"{personality_context}\n\n{rag_query}"
    if personality_context:
        return f"{personality_context}\n\nUser question: {user_query}"
    return rag_query


def should_attach_private_context_to_chat() -> bool:
    """False when remote OpenAI should only receive the user's live text input."""
    if (
        config.MODEL_PROVIDER == "openai"
        and config.CLOUD_TEXT_ONLY
        and not config.is_lan_safe_url(config.OPENAI_BASE_URL)
    ):
        return False
    return True

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Open Chat application...")
    
    # Initialize conversation storage
    await conversation_service.initialize()
    
    # Initialize RAG service
    await rag_service.initialize()
    await archive_service.initialize()
    await research_vault_service.initialize()
    
    # Test active provider connection
    active_service = get_active_chat_service()
    if await active_service.health_check():
        logger.info(f"✅ {config.MODEL_PROVIDER.title()} connection successful")
    else:
        logger.warning(f"⚠️  {config.MODEL_PROVIDER.title()} connection failed - check provider configuration")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Open Chat application...")

app = FastAPI(
    title="Open Chat",
    description="Voice and text chat with configurable OpenAI or Ollama models",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount only necessary static files for generated content
app.mount("/temp_audio", StaticFiles(directory="../temp_audio"), name="temp_audio")
app.mount("/audio", StaticFiles(directory="../temp_audio"), name="audio")
app.mount("/static", StaticFiles(directory="../frontend"), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the chat frontend."""
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
    """Get available models for the active provider, with vision capability info."""
    try:
        if config.MODEL_PROVIDER == "openai":
            models = await openai_service.get_available_models()
            vision_models = list(models)
        else:
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
            "provider": config.MODEL_PROVIDER,
            "default_model": get_default_chat_model(),
            "models": models,
            "models_with_info": models_with_vision,
            "vision_models": vision_models
        }
    except Exception as e:
        logger.error(f"Failed to fetch models: {e}")
        default_model = get_default_chat_model()
        return {
            "provider": config.MODEL_PROVIDER,
            "default_model": default_model,
            "models": [default_model],
            "models_with_info": [{"name": default_model, "supports_vision": config.MODEL_PROVIDER == "openai"}],
            "vision_models": [default_model] if config.MODEL_PROVIDER == "openai" else []
        }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    provider_connected = await get_active_chat_service().health_check()
    
    services = ["stt", "conversation"]
    if config.TTS_PROVIDER == "elevenlabs" and config.ELEVENLABS_API_KEY:
        services.append("tts-elevenlabs")
    else:
        services.append("tts-local")
    
    return HealthResponse(
        status="healthy" if provider_connected else "degraded",
        model_provider=config.MODEL_PROVIDER,
        provider_connected=provider_connected,
        ollama_connected=provider_connected if config.MODEL_PROVIDER == "ollama" else False,
        tts_provider=config.TTS_PROVIDER,
        services=services
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process chat message and return response"""
    try:
        if should_attach_private_context_to_chat():
            conversation_history = await conversation_service.get_recent_messages(6)
            rag_context = await enhance_chat_with_rag(request.message, rag_service, conversation_history)
            personality_context = await rag_service.get_persona_context()
            enhanced_query = merge_prompt_contexts(request.message, personality_context, rag_context["enhanced_query"])
            rag_sources = format_rag_sources(rag_context["sources"])
        else:
            enhanced_query = request.message
            rag_sources = []
        
        model = request.model or get_default_chat_model()
        active_service = get_active_chat_service()
        
        chat_result = await active_service.chat_with_functions(
            enhanced_query, 
            model,
            temperature=getattr(request, 'temperature', 0.7),
            top_p=getattr(request, 'top_p', 0.9)
        )
        
        response_text = chat_result.get("response", "")
        response_text = append_rag_citation_summary(response_text, rag_sources)
        ai_initiated = chat_result.get("ai_initiated", False)
        
        # Handle AI-initiated image generation
        generated_image = None
        if ai_initiated and "function_call" in chat_result:
            function_call = chat_result["function_call"]
            if function_call["name"] == "generate_image":
                try:
                    args = function_call["arguments"]
                    logger.info(f"🎨 AI-initiated image generation: {args.get('reason', 'Creative enhancement')}")
                    
                    # Generate image using intelligent ComfyUI selection
                    image_filename = await comfyui_service.generate_image(
                        prompt=args["prompt"],
                        style=args.get("style", "artistic")
                        # Let intelligent system handle negative_prompt, dimensions, steps, cfg
                    )
                    
                    if image_filename:
                        # Create URL for the generated image
                        image_url = f"/temp_audio/{image_filename}"
                        generated_image = GeneratedImage(
                            url=image_url,
                            prompt=args["prompt"],
                            reason=args.get("reason", "AI creative enhancement"),
                            style=args.get("style", "artistic"),
                            ai_initiated=True
                        )
                        logger.info(f"✅ AI successfully generated {args.get('style', 'artistic')} image: {image_url}")
                    else:
                        logger.error("AI-initiated image generation failed: No image returned from ComfyUI")
                        
                except Exception as e:
                    logger.error(f"Error in AI-initiated image generation: {e}")
        
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
            audio_file=audio_file,
            metadata={"rag_sources": [source.model_dump() for source in rag_sources]} if rag_sources else None
        )
        await conversation_service.save_message(assistant_msg)

        await research_vault_service.append_entry(
            "chat_exchange",
            {
                "user_message": request.message,
                "assistant_response": response_text,
                "provider": config.MODEL_PROVIDER,
                "model": model,
                "cloud_text_only": config.CLOUD_TEXT_ONLY,
                "rag_source_count": len(rag_sources),
                "generated_image": generated_image.model_dump() if generated_image else None,
                "timestamp": datetime.now().isoformat(),
            },
            model_name=model,
        )
        
        # Build response
        response = ChatResponse(
            response=response_text,
            model=model,
            timestamp=datetime.now(),
            audio_file=audio_file,
            rag_sources=rag_sources or None
        )
        
        # Add generated image to response if available
        if generated_image:
            response.generated_image = generated_image
        
        return response
        
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
        selected_model = model or get_default_chat_model()
        
        # Check if image is provided and model supports vision
        if image:
            if (
                config.MODEL_PROVIDER == "openai"
                and config.CLOUD_TEXT_ONLY
                and not config.is_lan_safe_url(config.OPENAI_BASE_URL)
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Image uploads are disabled while CLOUD_TEXT_ONLY is enabled for remote OpenAI. Use a local model for image analysis.",
                )

            # Validate image
            image_data = await image.read()
            if not vision_service.validate_image(image_data):
                raise HTTPException(status_code=400, detail="Invalid image format")
            
            # Get conversation context for better responses
            recent_messages = await conversation_service.get_recent_messages(5)
            context = [{"role": msg["role"], "content": msg["content"]} for msg in recent_messages]
            
            if config.MODEL_PROVIDER == "openai":
                response_text = await openai_service.chat_with_image(
                    message, image_data, selected_model, context
                )
            else:
                if not await vision_service.is_vision_model(selected_model):
                    vision_models = await vision_service.get_available_vision_models()
                    if vision_models:
                        selected_model = vision_models[0]
                        logger.info(f"Switched to vision model: {selected_model}")
                    else:
                        raise HTTPException(status_code=400, detail="No vision models available for image analysis")

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
            if should_attach_private_context_to_chat():
                conversation_history = await conversation_service.get_recent_messages(6)
                rag_context = await enhance_chat_with_rag(message, rag_service, conversation_history)
                rag_sources = format_rag_sources(rag_context["sources"])
                personality_context = await rag_service.get_persona_context()
                enhanced_query = merge_prompt_contexts(message, personality_context, rag_context["enhanced_query"])
            else:
                rag_sources = []
                enhanced_query = message
            if config.MODEL_PROVIDER == "openai":
                response_text = await openai_service.generate_response(enhanced_query, selected_model)
            else:
                response_text = await ollama_service.generate_response(enhanced_query, selected_model)
            response_text = append_rag_citation_summary(response_text, rag_sources)
            
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
            audio_file=audio_file,
            metadata={"rag_sources": [source.model_dump() for source in rag_sources]} if 'rag_sources' in locals() and rag_sources else None
        )
        await conversation_service.save_message(assistant_msg)

        await research_vault_service.append_entry(
            "chat_exchange",
            {
                "user_message": message,
                "assistant_response": response_text,
                "provider": config.MODEL_PROVIDER,
                "model": selected_model,
                "cloud_text_only": config.CLOUD_TEXT_ONLY,
                "image_uploaded": bool(image),
                "rag_source_count": len(rag_sources) if 'rag_sources' in locals() and rag_sources else 0,
                "timestamp": datetime.now().isoformat(),
            },
            model_name=selected_model,
        )
        
        return ChatResponse(
            response=response_text,
            model=selected_model,
            timestamp=datetime.now(),
            audio_file=audio_file,
            rag_sources=rag_sources if 'rag_sources' in locals() and rag_sources else None
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
        safe_filename = Path(file.filename).name
        temp_file_path = os.path.join(temp_dir, safe_filename)
        
        with open(temp_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        upload_file_hash = hashlib.sha256(content).hexdigest()
        
        upload_metadata = {
            "filename": file.filename,
            "content_type": file.content_type,
            "upload_time": datetime.now().isoformat(),
            "file_hash": upload_file_hash,
        }

        if file_extension == ".json":
            threads = parse_chatgpt_export_file(temp_file_path)
            if not threads:
                raise HTTPException(status_code=400, detail="Unsupported JSON file. Expected a ChatGPT conversations export.")

            imported_threads = 0
            skipped_duplicates = 0
            personality_memory_count = 0
            archive_document_count = 0
            formative_moments_count = 0
            legal_sensitive_threads = 0
            retention_counts = {"distill_only": 0, "exact_reference": 0}

            for thread in threads:
                thread_source = f"{safe_filename}::{thread['thread_filename']}"
                thread_metadata = {
                    **upload_metadata,
                    "source_kind": "chatgpt_export_thread",
                    "conversation_title": thread["title"],
                    "archive_type": thread["archive_type"],
                    "legal_sensitivity": thread["legal_sensitivity"],
                    "era_label": thread["era_label"],
                    "message_count": thread["message_count"],
                    "evidence_count": thread["evidence_count"],
                    "participants": thread["participants"],
                    "create_time": thread["create_time"],
                    "update_time": thread["update_time"],
                    "legal_relevance_manifest": thread["legal_relevance_manifest"],
                    "evidence_manifest": thread["evidence_manifest"],
                }

                prepared = await archive_service.prepare_document(
                    filename=thread["thread_filename"],
                    text=thread["text"],
                    metadata=thread_metadata,
                )

                retention_mode = prepared["retention_mode"]
                retention_counts[retention_mode] = retention_counts.get(retention_mode, 0) + 1

                if not prepared.get("duplicate") and retention_mode == "exact_reference":
                    success = await rag_service.add_text_document(
                        thread["text"],
                        source=thread_source,
                        metadata={
                            **thread_metadata,
                            "filename": thread["thread_filename"],
                            "retention_mode": retention_mode,
                            "content_hash": prepared.get("content_hash"),
                        },
                    )
                    if not success:
                        continue

                archive_result = await archive_service.process_document(
                    file_path=thread_source,
                    filename=thread["thread_filename"],
                    text=thread["text"],
                    metadata=thread_metadata,
                    precomputed=prepared,
                )

                if archive_result.get("skipped_duplicate"):
                    skipped_duplicates += 1
                    continue

                await research_vault_service.append_entry(
                    "archive_ingest",
                    {
                        "source_kind": "chatgpt_export_thread",
                        "parent_filename": file.filename,
                        "thread_title": thread["title"],
                        "thread_filename": thread["thread_filename"],
                        "raw_text": thread["text"],
                        "analysis": archive_result,
                        "metadata": thread_metadata,
                        "timestamp": datetime.now().isoformat(),
                    },
                    source_ref=thread_source,
                    file_hash=archive_result.get("file_hash"),
                    content_hash=archive_result.get("content_hash"),
                )

                imported_threads += 1
                archive_document_count += 1 if archive_result.get("archive_document_created") else 0
                personality_memory_count += 1 if archive_result.get("personality_memory_created") else 0
                formative_moments_count += int(archive_result.get("formative_moments_created", 0))
                legal_sensitive_threads += 1 if archive_result.get("legal_sensitivity") else 0

            if imported_threads == 0 and skipped_duplicates == 0:
                raise HTTPException(status_code=500, detail="Failed to import any conversations from the ChatGPT export")

            os.remove(temp_file_path)
            return {
                "message": f"Imported {imported_threads} conversation threads from '{file.filename}'",
                "imported_threads": imported_threads,
                "skipped_duplicates": skipped_duplicates,
                "archive_document_created": archive_document_count > 0,
                "archive_documents_created": archive_document_count,
                "personality_memory_created": personality_memory_count > 0,
                "personality_memories_created": personality_memory_count,
                "legal_sensitivity": legal_sensitive_threads > 0,
                "legal_sensitive_threads": legal_sensitive_threads,
                "formative_moments_created": formative_moments_count,
                "archive_type": "chatgpt_export",
                "era_label": None,
                "retention_counts": retention_counts,
                "file_hash": upload_file_hash,
            }

        extracted_text = await rag_service.extract_document_text(temp_file_path)
        prepared = await archive_service.prepare_document(
            filename=file.filename,
            text=extracted_text,
            metadata=upload_metadata,
            raw_bytes=content,
        )
        retention_mode = prepared["retention_mode"]

        success = True
        if not prepared.get("duplicate") and retention_mode == "exact_reference":
            success = await rag_service.add_document(
                temp_file_path,
                metadata={
                    **upload_metadata,
                    "retention_mode": retention_mode,
                    "content_hash": prepared.get("content_hash"),
                }
            )

        archive_result = await archive_service.process_document(
            file_path=temp_file_path,
            filename=file.filename,
            text=extracted_text,
            metadata=upload_metadata,
            precomputed=prepared,
        ) if success else {
            "archive_document_created": False,
            "personality_memory_created": False,
            "archive_type": "reference_document",
            "era_label": None,
            "legal_sensitivity": False,
            "formative_moments_created": 0,
            "retention_mode": retention_mode,
            "skipped_duplicate": False,
        }

        os.remove(temp_file_path)

        if success or archive_result.get("skipped_duplicate"):
            if not archive_result.get("skipped_duplicate"):
                await research_vault_service.append_entry(
                    "archive_ingest",
                    {
                        "source_kind": "single_document",
                        "filename": file.filename,
                        "raw_text": extracted_text,
                        "analysis": archive_result,
                        "metadata": upload_metadata,
                        "timestamp": datetime.now().isoformat(),
                    },
                    source_ref=temp_file_path,
                    file_hash=archive_result.get("file_hash"),
                    content_hash=archive_result.get("content_hash"),
                )
            return {
                "message": f"Document '{file.filename}' processed successfully",
                "personality_memory_created": archive_result.get("personality_memory_created", False),
                "archive_document_created": archive_result.get("archive_document_created", False),
                "archive_type": archive_result.get("archive_type"),
                "era_label": archive_result.get("era_label"),
                "legal_sensitivity": archive_result.get("legal_sensitivity", False),
                "formative_moments_created": archive_result.get("formative_moments_created", 0),
                "retention_mode": archive_result.get("retention_mode"),
                "skipped_duplicate": archive_result.get("skipped_duplicate", False),
                "duplicate_of": archive_result.get("duplicate_of"),
                "file_hash": archive_result.get("file_hash"),
                "content_hash": archive_result.get("content_hash"),
            }
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

@app.get("/archive/stats")
async def get_archive_stats():
    """Get archive-analysis statistics."""
    try:
        return archive_service.get_stats()
    except Exception as e:
        logger.error(f"Error getting archive stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/archive/documents")
async def get_archive_documents(limit: int = 100):
    """List analyzed archive documents."""
    try:
        return {"documents": await archive_service.list_documents(limit)}
    except Exception as e:
        logger.error(f"Error listing archive documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/archive/eras")
async def get_archive_eras():
    """List grouped archive eras."""
    try:
        return {"eras": await archive_service.list_eras()}
    except Exception as e:
        logger.error(f"Error listing archive eras: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/archive/formative-moments")
async def get_formative_moments(limit: int = 100):
    """List preserved formative moments."""
    try:
        return {"moments": await archive_service.list_formative_moments(limit)}
    except Exception as e:
        logger.error(f"Error listing formative moments: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/research-vault/stats")
async def get_research_vault_stats():
    """Return aggregate research-vault stats without exposing cleartext."""
    try:
        return research_vault_service.get_stats()
    except Exception as e:
        logger.error(f"Error getting research vault stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/research-vault")
async def wipe_research_vault():
    """Delete the entire encrypted research vault."""
    try:
        return await research_vault_service.wipe()
    except Exception as e:
        logger.error(f"Error wiping research vault: {e}")
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
    """Serve uploaded or generated images"""
    try:
        image_path = os.path.join(config.AUDIO_TEMP_DIR, filename)
        if os.path.exists(image_path):
            return FileResponse(image_path)
        else:
            raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
        logger.error(f"Error serving image: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ComfyUI Integration Endpoints
@app.get("/comfyui/status")
async def get_comfyui_status():
    """Get ComfyUI connection status and system info"""
    try:
        is_connected = await comfyui_service.health_check()
        system_info = await comfyui_service.get_system_info() if is_connected else {}
        queue_status = await comfyui_service.get_queue_status() if is_connected else {}
        
        return {
            "connected": is_connected,
            "base_url": comfyui_service.get_active_url(),
            "system_info": system_info,
            "queue_status": queue_status
        }
    except Exception as e:
        logger.error(f"Error getting ComfyUI status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/comfyui/models")
async def get_comfyui_models():
    """Get available ComfyUI models"""
    try:
        models = await comfyui_service.get_models()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error getting ComfyUI models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/comfyui/generate")
async def generate_image_comfyui(
    prompt: str = Form(...),
    negative_prompt: str = Form(""),
    width: int = Form(1024),
    height: int = Form(1024),
    steps: int = Form(20),
    cfg: float = Form(8.0),
    model: str = Form(None)
):
    """Generate an image using ComfyUI"""
    try:
        logger.info(f"Generating image with prompt: {prompt[:100]}...")
        
        # Generate the image
        image_filename = await comfyui_service.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            model=model
        )
        
        if image_filename:
            # Save generation info to conversation
            generation_msg = ChatMessage(
                role="assistant",
                content=f"🎨 Generated image: '{prompt[:50]}...' using ComfyUI",
                timestamp=datetime.now(),
                audio_file=None
            )
            await conversation_service.save_message(generation_msg)
            
            return {
                "success": True,
                "image_filename": image_filename,
                "prompt": prompt,
                "timestamp": datetime.now()
            }
        else:
            raise HTTPException(status_code=500, detail="Image generation failed")
            
    except Exception as e:
        logger.error(f"Error generating image: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.HOST,
        port=config.PORT,
        reload=False  # Temporarily disable reload for testing
    )
