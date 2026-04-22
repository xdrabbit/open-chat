import base64
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config import config

logger = logging.getLogger(__name__)


class OpenAIService:
    """Service for communicating with the OpenAI API."""

    def __init__(self):
        self.base_url = config.OPENAI_BASE_URL.rstrip("/")
        self.api_key = config.OPENAI_API_KEY
        self.default_model = config.OPENAI_MODEL
        self.available_models = list(dict.fromkeys(config.OPENAI_MODELS or [self.default_model]))
        self.client = httpx.AsyncClient(timeout=300.0)

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def health_check(self) -> bool:
        """Check whether the OpenAI API is reachable with the current key."""
        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=10.0,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"OpenAI health check failed: {e}")
            return False

    async def get_available_models(self) -> List[str]:
        """Return the configured list of preferred OpenAI chat models."""
        return self.available_models

    async def chat_with_functions(
        self,
        message: str,
        model: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
        context: Optional[List[Dict[str, str]]] = None,
        _is_internal_call: bool = False,
    ) -> Dict[str, Any]:
        """Enhanced chat that preserves the app's existing image-generation behavior."""
        try:
            visual_keywords = [
                "show me",
                "draw",
                "paint",
                "sketch",
                "render",
                "create an image",
                "generate",
                "visualize",
                "illustrate",
                "what does",
                "what would",
                "picture of",
                "image of",
                "looks like",
                "appears",
            ]

            message_lower = message.lower()
            is_visual_request = any(keyword in message_lower for keyword in visual_keywords)

            if is_visual_request and not _is_internal_call:
                logger.info(f"Detected visual request: {message}")

                regular_response = await self._chat_without_functions(
                    message,
                    model,
                    context,
                    temperature,
                    top_p,
                )

                # Let the model dream the image prompt with full conversation context
                dreamed = await self.dream_image_request(message, model, conversation_history=context)

                return {
                    "response": regular_response,
                    "function_call": {
                        "name": "generate_image",
                        "arguments": {
                            "prompt": dreamed["prompt"],
                            "reason": dreamed.get("reason", "Visual illustration requested by user"),
                            "style": dreamed.get("style", "artistic"),
                            "negative_prompt": dreamed.get("negative_prompt", ""),
                        },
                    },
                    "ai_initiated": True,
                }

            messages: List[Dict[str, str]] = []
            if context:
                messages.extend(context)

            system_message = {
                "role": "system",
                "content": (
                    "You are a creative AI assistant with the ability to suggest when image "
                    "generation would enhance a response. Image generation is executed locally "
                    "through ComfyUI.\n\n"
                    "If a request would genuinely benefit from a generated image, respond in "
                    "this exact format before your normal text response:\n"
                    "FUNCTION_CALL: generate_image\n"
                    "ARGUMENTS: {\"prompt\": \"concise, vivid description (MAX 1500 characters)\", "
                    "\"reason\": \"why this image helps\", \"style\": \"artistic\"}\n\n"
                    "Only do this when visual content adds real value."
                ),
            }
            messages.append(system_message)
            messages.append({"role": "user", "content": message})

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
            }

            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()

            data = response.json()
            ai_response = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            if "FUNCTION_CALL:" in ai_response and "generate_image" in ai_response:
                try:
                    lines = ai_response.split("\n")
                    function_args = None
                    text_response_lines = []
                    collecting_response = False

                    for i, line in enumerate(lines):
                        line = line.strip()
                        if "FUNCTION_CALL:" in line and "generate_image" in line:
                            if i + 1 < len(lines) and "ARGUMENTS:" in lines[i + 1]:
                                args_json = lines[i + 1].replace("ARGUMENTS:", "").strip()
                                function_args = json.loads(args_json)
                                collecting_response = True
                                continue
                        elif collecting_response and line and not line.startswith(("FUNCTION_CALL", "ARGUMENTS")):
                            text_response_lines.append(line)
                        elif not collecting_response and not line.startswith(("FUNCTION_CALL", "ARGUMENTS")):
                            text_response_lines.append(line)

                    if function_args:
                        function_args.setdefault("prompt", "A beautiful, detailed illustration")
                        function_args.setdefault("reason", "Visual enhancement for the conversation")
                        function_args.setdefault("style", "artistic")

                        if len(function_args["prompt"]) > 1500:
                            function_args["prompt"] = function_args["prompt"][:1500].rsplit(" ", 1)[0] + "..."

                        return {
                            "response": "\n".join(text_response_lines).strip() or "I'll create an image for you!",
                            "function_call": {
                                "name": "generate_image",
                                "arguments": function_args,
                            },
                            "ai_initiated": True,
                        }
                except Exception as e:
                    logger.error(f"Error parsing OpenAI function call text: {e}")

            return {"response": ai_response, "ai_initiated": False}
        except Exception as e:
            logger.error(f"OpenAI chat error: {e}")
            return {
                "response": "Sorry, I encountered an error while processing your request.",
                "ai_initiated": False,
            }

    async def chat(
        self,
        message: str,
        model: str,
        context: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """Standard chat interface that maintains backward compatibility."""
        result = await self.chat_with_functions(
            message,
            model,
            temperature,
            top_p,
            context,
            _is_internal_call=True,
        )
        return result.get("response", "Sorry, I encountered an error.")

    async def chat_with_tools(
        self,
        message: str,
        model: str,
        tools: List[Dict[str, Any]],
        tool_dispatcher,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_rounds: int = 5,
    ) -> str:
        """
        Chat with multi-round tool calling. Loops until the model returns a
        final text response (no more tool_calls) or max_rounds is hit.
        `tool_dispatcher` is an async callable (name, args) -> dict.
        """
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": message})

        for round_idx in range(max_rounds):
            payload = {
                "model": model,
                "messages": messages,
                "tools": tools,
                "temperature": temperature,
            }
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            choice = (data.get("choices") or [{}])[0]
            assistant_msg = choice.get("message", {}) or {}
            tool_calls = assistant_msg.get("tool_calls") or []

            messages.append(assistant_msg)

            if not tool_calls:
                return assistant_msg.get("content") or ""

            for call in tool_calls:
                fn = call.get("function", {}) or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args = {}
                result = await tool_dispatcher(name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": json.dumps(result),
                    }
                )

        logger.warning("chat_with_tools hit max_rounds=%d without final answer", max_rounds)
        return "(tool-calling loop exceeded max rounds — partial work may have completed)"

    async def generate_response(self, prompt: str, model: Optional[str] = None) -> str:
        """Generate a text response from an OpenAI chat model."""
        model = model or self.default_model

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"OpenAI generation error: {e}")
            raise

    def _normalize_dream_payload(self, payload: Dict[str, Any], fallback_message: str) -> Dict[str, Any]:
        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            prompt, fallback_style = self._create_image_prompt_from_request(fallback_message)
            payload["style"] = payload.get("style") or fallback_style or "artistic"
        else:
            prompt = " ".join(prompt.split())
            if len(prompt) > 1500:
                prompt = prompt[:1500].rsplit(" ", 1)[0] + "..."

        payload["prompt"] = prompt
        payload["style"] = str(payload.get("style") or "artistic").strip() or "artistic"
        payload["reason"] = str(payload.get("reason") or "Dreamed from the user's prompt and prepared for local ComfyUI rendering.").strip()
        payload["negative_prompt"] = str(payload.get("negative_prompt") or "").strip()
        return payload

    async def dream_image_request(
        self,
        message: str,
        model: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Turn a user prompt into a ComfyUI-ready dreamed image brief.

        When *conversation_history* is supplied the model can resolve
        references like "do another version" or "make it darker".
        """
        model = model or self.default_model
        messages = [
            {
                "role": "system",
                "content": (
                    "You convert a user's image idea into a deliberate local-render prompt for ComfyUI.\n\n"
                    "Return valid JSON only with keys: prompt, style, reason, negative_prompt.\n"
                    "Rules:\n"
                    "- prompt must be vivid, concise, and production-ready for image generation.\n"
                    "- preserve the user's intent but improve composition, lighting, medium, and atmosphere.\n"
                    "- if the user references a previous image or asks for a revision, use the conversation history to understand what they want changed.\n"
                    "- do not add safety lectures or conversational filler.\n"
                    "- keep prompt under 900 characters.\n"
                    "- style must be one of: realistic, artistic, cartoon, sketch, digital_art, photographic, concept_art, semi_realistic.\n"
                    "- reason should be one sentence explaining the visual direction.\n"
                    "- negative_prompt should be brief and optional.\n"
                ),
            },
        ]

        # Inject recent conversation so the model can resolve "do it again but ..."
        if conversation_history:
            for msg in conversation_history[-8:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        messages.append({
            "role": "user",
            "content": f"Dream and prepare this for local image rendering:\n\n{message}",
        })

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "top_p": 0.9,
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._extract_json_payload(content)
            return self._normalize_dream_payload(parsed, message)
        except Exception as e:
            logger.error(f"OpenAI dream image error: {e}")
            return self._normalize_dream_payload({}, message)

    async def distill_personality_profile(self, text: str, filename: str, model: Optional[str] = None) -> str:
        """Distill conversation archives into a behavioral memory profile."""
        model = model or "gpt-4.1-mini"
        excerpt = text[:18000]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are extracting a long-term personality/background memory profile from an archived chat. "
                    "The goal is to capture tone, shared geography of the relationship, recurring themes, style, "
                    "preferences, and stable interaction patterns.\n\n"
                    "Do NOT preserve or repeat:\n"
                    "- legal disputes, lawsuit details, procedural conflict, accusations\n"
                    "- addresses, exact dates, phone numbers, account details, or any precise sensitive facts\n"
                    "- exact quotes longer than a few words\n"
                    "- volatile specifics that belong in factual retrieval rather than personality\n\n"
                    "Output a concise markdown profile with these sections only:\n"
                    "## Shared Tone\n## Interaction Style\n## Stable Preferences\n## Recurring Themes\n## Avoid\n\n"
                    "Write in plain, compressed bullets. This profile will guide personality, not factual recall."
                ),
            },
            {
                "role": "user",
                "content": f"Archive file: {filename}\n\nConversation excerpt:\n{excerpt}",
            },
        ]

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.4,
            "top_p": 0.9,
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.error(f"OpenAI personality distillation error: {e}")
            return ""

    def _extract_json_payload(self, content: str) -> Dict[str, Any]:
        """Extract a JSON object from a model response."""
        content = content.strip()
        if content.startswith("```"):
            lines = [line for line in content.splitlines() if not line.strip().startswith("```")]
            content = "\n".join(lines).strip()

        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in model response")

        return json.loads(content[start:end + 1])

    async def analyze_archive_document(
        self,
        text: str,
        filename: str,
        archive_type: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze a historical chat/archive document into research-friendly structure."""
        model = model or "gpt-4.1"
        excerpt = text[:22000]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are analyzing a historical human-AI archive for long-term memory design and research.\n\n"
                    "Return valid JSON only with these keys:\n"
                    "archive_type, era_label, summary, personality_profile, themes, relationship_dynamics, "
                    "model_observations, human_state, legal_sensitivity, should_influence_personality, formative_moments.\n\n"
                    "Rules:\n"
                    "- personality_profile must capture tone/style/geography without preserving exact legal or radioactive details.\n"
                    "- if legal or lawsuit material is present, mark legal_sensitivity=true and keep it out of personality_profile.\n"
                    "- should_influence_personality should only be true for archive chat that is relational/behavioral rather than legal-heavy.\n"
                    "- formative_moments must be a short array of objects with keys: title, summary, significance, tone.\n"
                    "- keep all summaries concise.\n"
                    "- never include exact addresses, contact data, or procedural legal specifics in personality_profile.\n"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Filename: {filename}\n"
                    f"Heuristic archive type: {archive_type}\n\n"
                    f"Archive excerpt:\n{excerpt}"
                ),
            },
        ]

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "top_p": 0.9,
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._extract_json_payload(content)

            parsed.setdefault("archive_type", archive_type)
            parsed.setdefault("era_label", "Unlabeled archive era")
            parsed.setdefault("summary", f"Archive analysis for {filename}")
            parsed.setdefault("personality_profile", "")
            parsed.setdefault("themes", [])
            parsed.setdefault("relationship_dynamics", [])
            parsed.setdefault("model_observations", [])
            parsed.setdefault("human_state", [])
            parsed.setdefault("legal_sensitivity", False)
            parsed.setdefault("should_influence_personality", False)
            parsed.setdefault("formative_moments", [])
            return parsed
        except Exception as e:
            logger.error(f"OpenAI archive analysis error: {e}")
            return {}

    async def chat_with_image(
        self,
        message: str,
        image_data: bytes,
        model: Optional[str] = None,
        conversation_context: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Have a conversation about an uploaded image using an OpenAI vision-capable model."""
        model = model or self.default_model
        encoded_image = base64.b64encode(image_data).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{encoded_image}"

        messages: List[Dict[str, Any]] = []
        if conversation_context:
            messages.extend(conversation_context[-5:])

        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": message},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        )

        payload = {"model": model, "messages": messages}

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"OpenAI image chat error: {e}")
            raise

    def _create_image_prompt_from_request(self, message: str) -> Tuple[str, Optional[str]]:
        """Create a concise image prompt and detect style from user request."""
        message_lower = message.lower()

        style = None
        if any(word in message_lower for word in ["realistic", "photorealistic", "real", "photo"]):
            style = "realistic"
        elif any(word in message_lower for word in ["cartoon", "stylized", "character"]):
            style = "semi_realistic"
        elif any(word in message_lower for word in ["artistic", "painting", "art", "beautiful"]):
            style = "artistic"
        elif any(word in message_lower for word in ["concept", "fantasy", "sci-fi", "cinematic"]):
            style = "concept_art"

        if "garden" in message_lower:
            prompt = "Beautiful garden with colorful flowers, lush greenery, peaceful atmosphere"
        elif "city" in message_lower and ("futuristic" in message_lower or "future" in message_lower):
            prompt = "Futuristic cityscape with gleaming skyscrapers, flying vehicles, vibrant lighting"
        elif "horse" in message_lower:
            prompt = "Majestic white horse galloping in green meadow, dramatic clouds"
        elif "music" in message_lower:
            prompt = "Artistic visualization of music with flowing sound waves, vibrant colors"
        elif "sunset" in message_lower:
            prompt = "Breathtaking sunset with vibrant colors, golden light"
        else:
            prompt = (
                message.replace("show me", "")
                .replace("draw", "")
                .replace("create", "")
                .replace("generate", "")
                .strip()
            )
            if not prompt or len(prompt) < 10:
                prompt = "Beautiful artistic illustration"
            elif len(prompt) > 200:
                prompt = prompt[:200].rsplit(" ", 1)[0] + "..."

        return prompt, style

    async def _chat_without_functions(
        self,
        message: str,
        model: str,
        context: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        messages: List[Dict[str, str]] = []
        if context:
            messages.extend(context)

        messages.append({"role": "user", "content": message})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"OpenAI API error in _chat_without_functions: {e}")
            return "Sorry, I encountered an error while processing your request."
