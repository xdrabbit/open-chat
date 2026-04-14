import logging
from datetime import datetime
from typing import Any, Dict, Optional

from config import config
from models.schemas import ChatMessage, ChatResponse, GeneratedImage

logger = logging.getLogger(__name__)


class DrawOrchestrator:
    """Own the deliberate and AI-initiated draw pipelines."""

    def __init__(self, comfyui_service, conversation_service, research_vault_service):
        self.comfyui_service = comfyui_service
        self.conversation_service = conversation_service
        self.research_vault_service = research_vault_service

    async def maybe_generate_ai_image(self, chat_result: Dict[str, Any]) -> Optional[GeneratedImage]:
        """Render an image when the chat model explicitly requested one."""
        if not chat_result.get("ai_initiated") or "function_call" not in chat_result:
            return None

        function_call = chat_result["function_call"]
        if function_call.get("name") != "generate_image":
            return None

        try:
            args = function_call.get("arguments", {})
            logger.info(f"🎨 AI-initiated image generation: {args.get('reason', 'Creative enhancement')}")

            image_filename = await self.comfyui_service.generate_image(
                prompt=args["prompt"],
                negative_prompt=args.get("negative_prompt", ""),
                style=args.get("style", "artistic"),
            )
            if not image_filename:
                logger.error("AI-initiated image generation failed: No image returned from ComfyUI")
                return None

            image_url = f"/temp_audio/{image_filename}"
            generated_image = GeneratedImage(
                url=image_url,
                prompt=args["prompt"],
                reason=args.get("reason", "AI creative enhancement"),
                style=args.get("style", "artistic"),
                ai_initiated=True,
            )
            logger.info(f"✅ AI successfully generated {generated_image.style or 'artistic'} image: {image_url}")
            return generated_image
        except Exception as e:
            logger.error(f"Error in AI-initiated image generation: {e}")
            return None

    async def run_dream_draw(self, request, model: str, active_service) -> ChatResponse:
        """Take a direct prompt, dream a render brief, and send it to ComfyUI."""
        dreamed = await active_service.dream_image_request(request.message, model)
        image_filename = await self.comfyui_service.generate_image(
            prompt=dreamed["prompt"],
            negative_prompt=dreamed.get("negative_prompt", ""),
            style=dreamed.get("style", "artistic"),
        )

        if not image_filename:
            raise RuntimeError("Local ComfyUI generation failed")

        response_text = (
            "Dreamed prompt sent to local ComfyUI.\n\n"
            f"{dreamed.get('reason', 'Prepared for rendering.')}"
        )

        generated_image = GeneratedImage(
            url=f"/temp_audio/{image_filename}",
            prompt=dreamed["prompt"],
            reason=dreamed.get("reason", "Dreamed locally and rendered with ComfyUI."),
            style=dreamed.get("style", "artistic"),
            ai_initiated=True,
        )

        user_msg = ChatMessage(
            role="user",
            content=f"/draw {request.message}",
            timestamp=datetime.now(),
        )
        await self.conversation_service.save_message(user_msg)

        assistant_msg = ChatMessage(
            role="assistant",
            content=response_text,
            timestamp=datetime.now(),
            metadata={
                "generated_image": generated_image.model_dump(),
                "image_command": "dream_draw",
            },
        )
        await self.conversation_service.save_message(assistant_msg)

        await self.research_vault_service.append_entry(
            "dream_draw",
            {
                "user_message": request.message,
                "dream_prompt": dreamed["prompt"],
                "reason": dreamed.get("reason"),
                "style": dreamed.get("style"),
                "provider": config.MODEL_PROVIDER,
                "model": model,
                "timestamp": datetime.now().isoformat(),
            },
            model_name=model,
        )

        return ChatResponse(
            response=response_text,
            model=model,
            timestamp=datetime.now(),
            generated_image=generated_image,
            rag_sources=[],
        )
