from datetime import datetime
from typing import Callable, List

from config import config
from models.schemas import ChatMessage, ChatResponse, RAGSource


class ChatOrchestrator:
    """Assemble chat context, invoke the active model, and persist the exchange."""

    def __init__(
        self,
        conversation_service,
        rag_service,
        tts_service,
        research_vault_service,
        draw_orchestrator,
        policy_service,
        default_model_getter: Callable[[], str],
        active_service_getter: Callable,
    ):
        self.conversation_service = conversation_service
        self.rag_service = rag_service
        self.tts_service = tts_service
        self.research_vault_service = research_vault_service
        self.draw_orchestrator = draw_orchestrator
        self.policy_service = policy_service
        self.default_model_getter = default_model_getter
        self.active_service_getter = active_service_getter

    def should_attach_private_context(self) -> bool:
        return self.policy_service.should_attach_private_context()

    @staticmethod
    def format_rag_sources(raw_sources) -> List[RAGSource]:
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

    @staticmethod
    def append_rag_citation_summary(response_text: str, rag_sources: List[RAGSource]) -> str:
        if not rag_sources:
            return response_text

        summary_lines = ["", "Sources:"]
        for source in rag_sources:
            summary_lines.append(
                f"[{source.source_id}] {source.filename} (chunk {source.chunk_index + 1}/{source.total_chunks})"
            )

        return f"{response_text.rstrip()}\n" + "\n".join(summary_lines)

    @staticmethod
    def merge_prompt_contexts(user_query: str, personality_context: str, rag_query: str) -> str:
        if personality_context and rag_query != user_query:
            return f"{personality_context}\n\n{rag_query}"
        if personality_context:
            return f"{personality_context}\n\nUser question: {user_query}"
        return rag_query

    async def build_chat_inputs(self, request_message: str, enhance_chat_with_rag):
        if self.should_attach_private_context():
            conversation_history = await self.conversation_service.get_recent_messages(6)
            rag_context = await enhance_chat_with_rag(request_message, self.rag_service, conversation_history)
            personality_context = await self.rag_service.get_persona_context()
            enhanced_query = self.merge_prompt_contexts(
                request_message,
                personality_context,
                rag_context["enhanced_query"],
            )
            rag_sources = self.format_rag_sources(rag_context["sources"])
        else:
            enhanced_query = request_message
            rag_sources = []

        return enhanced_query, rag_sources

    async def handle_chat(self, request, enhance_chat_with_rag) -> ChatResponse:
        enhanced_query, rag_sources = await self.build_chat_inputs(request.message, enhance_chat_with_rag)
        model = request.model or self.default_model_getter()
        active_service = self.active_service_getter()

        chat_result = await active_service.chat_with_functions(
            enhanced_query,
            model,
            temperature=getattr(request, "temperature", 0.7),
            top_p=getattr(request, "top_p", 0.9),
        )

        response_text = self.append_rag_citation_summary(chat_result.get("response", ""), rag_sources)
        generated_image = await self.draw_orchestrator.maybe_generate_ai_image(chat_result)

        user_msg = ChatMessage(
            role="user",
            content=request.message,
            timestamp=datetime.now(),
        )
        await self.conversation_service.save_message(user_msg)

        audio_file = None
        try:
            audio_file = await self.tts_service.generate_speech(response_text, request.voice_id)
        except Exception:
            audio_file = None

        assistant_msg = ChatMessage(
            role="assistant",
            content=response_text,
            timestamp=datetime.now(),
            audio_file=audio_file,
            metadata={"rag_sources": [source.model_dump() for source in rag_sources]} if rag_sources else None,
        )
        await self.conversation_service.save_message(assistant_msg)

        await self.research_vault_service.append_entry(
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

        response = ChatResponse(
            response=response_text,
            model=model,
            timestamp=datetime.now(),
            audio_file=audio_file,
            rag_sources=rag_sources or None,
        )
        if generated_image:
            response.generated_image = generated_image
        return response
