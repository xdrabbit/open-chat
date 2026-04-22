from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import logging
from datetime import datetime
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
from services.chat_orchestrator import ChatOrchestrator
from services.draw_orchestrator import DrawOrchestrator
from services.policy_service import PolicyService
from services.ingest_orchestrator import IngestOrchestrator
from services.mission_control_service import (
    TOOL_SCHEMAS as MC_TOOL_SCHEMAS,
    build_system_prompt as build_mc_system_prompt,
    dispatch_tool_call as mc_dispatch_tool_call,
)

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
policy_service = PolicyService()


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


draw_orchestrator = DrawOrchestrator(comfyui_service, conversation_service, research_vault_service)
chat_orchestrator = ChatOrchestrator(
    conversation_service,
    rag_service,
    tts_service,
    research_vault_service,
    draw_orchestrator,
    policy_service,
    get_default_chat_model,
    get_active_chat_service,
)
ingest_orchestrator = IngestOrchestrator(
    rag_service,
    archive_service,
    research_vault_service,
    policy_service,
    parse_chatgpt_export_file,
)


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
        return await chat_orchestrator.handle_chat(request, enhance_chat_with_rag)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mc-chat")
async def mission_control_chat(request: ChatRequest):
    """
    Mission Control chat endpoint. Routes the user's message to the active
    chat service (OpenAI or Ollama) with MC tool schemas attached, so the
    model can log accomplishments and manage goals via tool calls.

    Bypasses RAG, image generation, and TTS — but DOES persist the exchange
    to conversation_service with metadata.source="mc-chat" so the chat is
    searchable later alongside regular open-chat conversations.
    """
    try:
        model = request.model or get_default_chat_model()
        active_service = get_active_chat_service()
        if not hasattr(active_service, "chat_with_tools"):
            raise HTTPException(
                status_code=501,
                detail=(
                    f"Active chat service ({type(active_service).__name__}) doesn't "
                    "support tool calling yet. Set MODEL_PROVIDER=openai or add "
                    "chat_with_tools to the provider's service."
                ),
            )

        # Persist user message before calling the model so we don't lose it on error.
        try:
            await conversation_service.save_message(ChatMessage(
                role="user",
                content=request.message,
                timestamp=datetime.now(),
                metadata={"source": "mc-chat", "model": model},
            ))
        except Exception:
            logger.warning("failed to persist mc-chat user message; continuing")

        reply = await active_service.chat_with_tools(
            message=request.message,
            model=model,
            tools=MC_TOOL_SCHEMAS,
            tool_dispatcher=mc_dispatch_tool_call,
            system_prompt=build_mc_system_prompt(),
        )

        try:
            await conversation_service.save_message(ChatMessage(
                role="assistant",
                content=reply,
                timestamp=datetime.now(),
                metadata={"source": "mc-chat", "model": model},
            ))
        except Exception:
            logger.warning("failed to persist mc-chat assistant message; continuing")

        return {"response": reply, "model": model}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("MC chat error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/dream-draw", response_model=ChatResponse)
async def chat_dream_draw(request: ChatRequest):
    """Take a direct prompt, have the active model dream a render brief, then send it to ComfyUI."""
    try:
        model = request.model or get_default_chat_model()
        active_service = get_active_chat_service()
        return await draw_orchestrator.run_dream_draw(request, model, active_service)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dream draw error: {e}")
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
                and not policy_service.allow_remote_image_upload()
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
            if chat_orchestrator.should_attach_private_context():
                conversation_history = await conversation_service.get_recent_messages(6)
                rag_context = await enhance_chat_with_rag(message, rag_service, conversation_history)
                rag_sources = chat_orchestrator.format_rag_sources(rag_context["sources"])
                personality_context = await rag_service.get_persona_context()
                enhanced_query = chat_orchestrator.merge_prompt_contexts(message, personality_context, rag_context["enhanced_query"])
            else:
                rag_sources = []
                enhanced_query = message
            if config.MODEL_PROVIDER == "openai":
                response_text = await openai_service.generate_response(enhanced_query, selected_model)
            else:
                response_text = await ollama_service.generate_response(enhanced_query, selected_model)
            response_text = chat_orchestrator.append_rag_citation_summary(response_text, rag_sources)
            
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
async def upload_document(
    file: UploadFile = File(...),
    ingest_intent: str = Form("auto"),
):
    """Upload and process a document for RAG"""
    try:
        return await ingest_orchestrator.handle_upload(file, ingest_intent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        detail = str(e)
        status_code = 503 if detail == "RAG service is not available" else 500
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/rag/status")
async def get_rag_status():
    """RAG health check — quick overview of whether retrieval is operational."""
    try:
        stats = rag_service.get_stats()
        return {
            "enabled": rag_service.is_enabled(),
            "available": stats.get("total_chunks", 0) > 0,
            "document_count": stats.get("total_chunks", 0),
            "collection": "rag_vectors",
            "embedding_model": stats.get("model"),
            "persona_memories": stats.get("persona_memories", 0),
        }
    except Exception as e:
        logger.error(f"Error getting RAG status: {e}")
        return {
            "enabled": False,
            "available": False,
            "document_count": 0,
            "collection": "rag_vectors",
            "embedding_model": None,
            "persona_memories": 0,
        }

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

@app.delete("/archive/documents/{document_id}")
async def delete_archive_document(document_id: str):
    """Remove an archive document from archive storage, RAG, and persona memory."""
    try:
        result = await archive_service.delete_document(document_id)
        if not result.get("deleted"):
            raise HTTPException(status_code=404, detail="Archive document not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting archive document {document_id}: {e}")
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

@app.get("/research-vault/report", response_model=ResearchVaultReportResponse)
async def get_research_vault_report(mode: str = "brief", limit: int = 0):
    """Return a synthesized research readout without exposing raw vault entries."""
    try:
        normalized_mode = mode.lower().strip()
        if normalized_mode not in {"brief", "full"}:
            raise HTTPException(status_code=400, detail="mode must be 'brief' or 'full'")

        effective_limit = limit
        if effective_limit <= 0:
            effective_limit = 24 if normalized_mode == "brief" else 72

        report_context = research_vault_service.build_report_context(limit=max(1, min(effective_limit, 240)))
        stats = report_context.get("stats", {})

        if not report_context.get("enabled", False):
            return ResearchVaultReportResponse(
                mode=normalized_mode,
                generated_at=datetime.now(),
                stats=stats,
                report="Research vault is disabled.",
                sections={"current_state": "Research vault is disabled."},
            )

        if report_context.get("entries_considered", 0) == 0:
            return ResearchVaultReportResponse(
                mode=normalized_mode,
                generated_at=datetime.now(),
                stats=stats,
                report="Research vault is empty. No findings yet.",
                sections={"current_state": "Research vault is empty. No findings yet."},
            )

        report_payload = {}
        if await ollama_service.health_check():
            report_payload = await ollama_service.generate_research_report(
                report_context,
                mode=normalized_mode,
            )

        if not report_payload:
            report_payload = research_vault_service.build_report_fallback(report_context, normalized_mode)

        return ResearchVaultReportResponse(
            mode=normalized_mode,
            generated_at=datetime.now(),
            stats=stats,
            report=report_payload.get("report", "No research report generated."),
            sections=report_payload.get("sections", {"current_state": "No research report generated."}),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating research vault report: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/research-vault/brief", response_model=ResearchVaultReportResponse)
async def get_research_vault_brief(limit: int = 24):
    """Convenience endpoint for a brief research readout."""
    return await get_research_vault_report(mode="brief", limit=limit)

@app.get("/research-vault/full-report", response_model=ResearchVaultReportResponse)
async def get_research_vault_full_report(limit: int = 72):
    """Convenience endpoint for a fuller research readout."""
    return await get_research_vault_report(mode="full", limit=limit)

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
