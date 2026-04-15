import httpx
import json
import logging
from typing import Optional, AsyncGenerator, Dict, Any, List, Tuple
from config import config

logger = logging.getLogger(__name__)

class OllamaService:
    """Service for communicating with Ollama API"""
    
    def __init__(self):
        self.base_url = config.OLLAMA_HOST
        self.default_model = config.OLLAMA_MODEL
        self.client = httpx.AsyncClient(timeout=300.0)
        
    async def health_check(self) -> bool:
        """Check if Ollama is running and accessible"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False
    
    async def get_available_models(self) -> list:
        """Get list of available models from Ollama"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
            return []
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []

    def get_available_functions(self) -> List[Dict[str, Any]]:
        """Define functions that AI can call"""
        return [
            {
                "name": "generate_image",
                "description": "Generate an image to illustrate, enhance, or visualize concepts in the conversation. Use this when the user asks for visual content, when explaining complex ideas that would benefit from illustration, or when you think an image would significantly improve your response.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Detailed, descriptive prompt for image generation. Be specific about style, composition, lighting, and mood."
                        },
                        "reason": {
                            "type": "string", 
                            "description": "Brief explanation of why this image would enhance the conversation or response."
                        },
                        "style": {
                            "type": "string",
                            "description": "Art style preference: realistic, artistic, cartoon, sketch, digital art, photographic, etc.",
                            "enum": ["realistic", "artistic", "cartoon", "sketch", "digital_art", "photographic", "concept_art"]
                        }
                    },
                    "required": ["prompt", "reason"]
                }
            }
        ]

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
        conversation_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Turn a user prompt into a ComfyUI-ready dreamed image brief.

        When *conversation_history* is supplied the model can resolve
        references like "do another version" or "make it darker" because
        it sees what came before.
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
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
            },
        }

        try:
            response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "")
            parsed = self._extract_json_payload(content)
            return self._normalize_dream_payload(parsed, message)
        except Exception as e:
            logger.error(f"Ollama dream image error: {e}")
            return self._normalize_dream_payload({}, message)

    async def analyze_archive_document(
        self,
        text: str,
        filename: str,
        archive_type: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze an archive document locally with Ollama."""
        model = model or self.default_model
        excerpt = text[:22000]

        payload = {
            "model": model,
            "messages": [
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
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }

        try:
            response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "")
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
            logger.error(f"Ollama archive analysis error: {e}")
            return {}

    async def generate_research_report(
        self,
        report_context: Dict[str, Any],
        mode: str = "brief",
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a non-verbatim research report from encrypted-vault context."""
        if model:
            selected_model = model
        elif mode == "full":
            selected_model = config.RESEARCH_REPORT_FULL_MODEL or config.RESEARCH_REPORT_MODEL or self.default_model
        else:
            selected_model = config.RESEARCH_REPORT_MODEL or self.default_model

        context_limit = 24000 if mode == "full" else 12000
        context_excerpt = json.dumps(report_context, ensure_ascii=False)[:context_limit]

        payload = {
            "model": selected_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a sealed research analyst for a private human-AI archive.\n\n"
                        "Return valid JSON only with keys: report, sections.\n"
                        "sections must be an object with keys: current_state, human_patterns, model_patterns, "
                        "relationship_dynamics, caution_flags, recommendations.\n\n"
                        "Rules:\n"
                        "- Never quote user or model text verbatim.\n"
                        "- Never reveal raw archive excerpts, exact legal details, addresses, or reconstructive transcript text.\n"
                        "- Speak only in synthesized observations, patterns, tendencies, and high-level summaries.\n"
                        "- Treat legal-sensitive material as quarantined context: it may inform caution_flags but must not dominate personality interpretation.\n"
                        "- `brief` mode should be concise and executive. `full` mode should read like a serious internal research memo.\n"
                        "- Be willing to say when evidence is thin.\n"
                        "- Focus on longitudinal change over time, not single incidents.\n"
                        "- Pay attention to attachment, rupture/repair, confidence loss and recovery, technical learning, model-update reactions, and the interaction of isolation with AI companionship.\n"
                        "- Distinguish stable traits from stress artifacts.\n"
                        "- Note whether the archive suggests the AI functioned as tutor, witness, mirror, collaborator, or attachment object, and how that changed.\n"
                        "- Recommendations should be concrete and oriented toward future memory/system design, not therapy advice.\n"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Mode: {mode}\n"
                        "Prepare the current research readout from this vault context.\n"
                        "Make it specific to this archive rather than generic. Use the available aggregates, eras, chat samples, and archive analyses to infer actual patterns.\n"
                        "If there is evidence of software-learning acceleration, legal-stress contamination, dependency, withdrawal, re-engagement, or changes across model eras, name that directly in synthesized form.\n\n"
                        f"{context_excerpt}"
                    ),
                },
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }

        try:
            response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "")
            parsed = self._extract_json_payload(content)
            parsed.setdefault("report", "No research report generated.")
            parsed.setdefault(
                "sections",
                {
                    "current_state": "",
                    "human_patterns": "",
                    "model_patterns": "",
                    "relationship_dynamics": "",
                    "caution_flags": "",
                    "recommendations": "",
                },
            )
            return parsed
        except Exception as e:
            logger.error(f"Ollama research report error: {e}")
            return {}

    async def chat_with_functions(
        self, 
        message: str, 
        model: str, 
        temperature: float = 0.7,
        top_p: float = 0.9,
        context: Optional[List[Dict]] = None,
        _is_internal_call: bool = False
    ) -> Dict[str, Any]:
        """Enhanced chat with function calling capability"""
        try:
            # Check if this is a visual request that should trigger image generation
            visual_keywords = [
                "show me", "draw", "paint", "sketch", "render", "create an image", "generate", "visualize", "illustrate", 
                "what does", "what would", "picture of", "image of", "looks like", "appears"
            ]
            
            message_lower = message.lower()
            is_visual_request = any(keyword in message_lower for keyword in visual_keywords)
            
            if is_visual_request and not _is_internal_call:
                logger.info(f"Detected visual request: {message}")

                # Get a regular chat response first (avoid recursion by calling base chat directly)
                regular_response = await self._chat_without_functions(message, model, context, temperature, top_p)

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
                        }
                    },
                    "ai_initiated": True
                }
            
            # Build conversation context
            messages = []
            if context:
                messages.extend(context)
            
            # Add system message with function calling instructions
            system_message = {
                "role": "system",
                "content": """You are a creative AI assistant with the ability to generate images to enhance your responses. Image generation runs locally through ComfyUI.

Consider generating images when:
- User asks to "show", "draw", "illustrate", "visualize", or "create" something visual
- Explaining complex concepts that would benefit from diagrams or illustrations
- Creative requests that need visual inspiration or examples
- User asks "what would X look like?" or similar visual questions
- You think an image would significantly improve understanding or engagement

When you decide to generate an image, use the generate_image function with a detailed, creative prompt. Always explain your reasoning and how the image relates to your response.

Be creative and helpful, but only generate images when they truly add value to the conversation."""
            }
            messages.append(system_message)
            
            # Add user message
            messages.append({
                "role": "user",
                "content": message
            })
            
            # First, get AI response with function calling capability
            function_prompt = f"""
{message}

You have access to image generation capabilities. If this request would benefit from a visual illustration, you can generate an image by responding in this exact format:

FUNCTION_CALL: generate_image
ARGUMENTS: {{"prompt": "concise, vivid description (MAX 1500 characters)", "reason": "why this image helps", "style": "artistic"}}

Then continue with your normal text response after the function call.

IMPORTANT: Keep image prompts under 1500 characters - be specific but concise. Focus on key visual elements, style, and mood rather than long descriptions.

Only use the function call if the user's request would genuinely benefit from visual content. If it's just a regular question, respond normally without any function call.
"""

            payload = {
                "model": model,
                "messages": messages[:-1] + [{"role": "user", "content": function_prompt}],
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "top_p": top_p
                }
            }
            
            response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                ai_response = data["message"]["content"]
                
                # Debug: Log the AI response to see what it's generating
                logger.info(f"AI Response: {ai_response[:200]}...")
                
                # Check if AI wants to call a function
                if "FUNCTION_CALL:" in ai_response and "generate_image" in ai_response:
                    try:
                        # Extract function call - look for the pattern more carefully
                        lines = ai_response.split('\n')
                        function_args = None
                        text_response_lines = []
                        
                        collecting_response = False
                        
                        for i, line in enumerate(lines):
                            line = line.strip()
                            if "FUNCTION_CALL:" in line and "generate_image" in line:
                                # Look for arguments on next line or same line
                                if i + 1 < len(lines) and "ARGUMENTS:" in lines[i + 1]:
                                    args_line = lines[i + 1].strip()
                                    args_json = args_line.replace("ARGUMENTS:", "").strip()
                                    try:
                                        function_args = json.loads(args_json)
                                        collecting_response = True
                                        continue
                                    except json.JSONDecodeError:
                                        pass
                                elif "ARGUMENTS:" in line:
                                    # Arguments on same line
                                    parts = line.split("ARGUMENTS:", 1)
                                    if len(parts) > 1:
                                        args_json = parts[1].strip()
                                        try:
                                            function_args = json.loads(args_json)
                                            collecting_response = True
                                            continue
                                        except json.JSONDecodeError:
                                            pass
                            elif collecting_response and line and not line.startswith("FUNCTION_CALL") and not line.startswith("ARGUMENTS"):
                                text_response_lines.append(line)
                            elif not collecting_response and not "FUNCTION_CALL" in line and not "ARGUMENTS" in line:
                                text_response_lines.append(line)
                        
                        if function_args:
                            # Ensure required fields are present
                            if "prompt" not in function_args:
                                function_args["prompt"] = "A beautiful, detailed illustration"
                            if "reason" not in function_args:
                                function_args["reason"] = "Visual enhancement for the conversation"
                            if "style" not in function_args:
                                function_args["style"] = "artistic"
                            
                            # Enforce 1500 character limit on prompt
                            if len(function_args["prompt"]) > 1500:
                                function_args["prompt"] = function_args["prompt"][:1500].rsplit(' ', 1)[0] + "..."
                                logger.info(f"Truncated image prompt to 1500 characters")
                            
                            return {
                                "response": '\n'.join(text_response_lines).strip() if text_response_lines else "I'll create an image for you!",
                                "function_call": {
                                    "name": "generate_image",
                                    "arguments": function_args
                                },
                                "ai_initiated": True
                            }
                    except Exception as e:
                        logger.error(f"Error parsing function call: {e}")
                        # Fall back to normal response
                        pass
                
                return {
                    "response": ai_response,
                    "ai_initiated": False
                }
            else:
                logger.error(f"Ollama chat error: {response.status_code} - {response.text}")
                return {"response": "Sorry, I encountered an error while processing your request.", "ai_initiated": False}
                
        except Exception as e:
            logger.error(f"Chat with functions error: {e}")
            return {"response": "Sorry, I encountered an error while processing your request.", "ai_initiated": False}

    async def chat(
        self, 
        message: str, 
        model: str, 
        context: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        top_p: float = 0.9
    ) -> str:
        """Standard chat interface that maintains backward compatibility"""
        result = await self.chat_with_functions(message, model, temperature, top_p, context, _is_internal_call=True)
        return result.get("response", "Sorry, I encountered an error.")
    
    async def generate_response(self, prompt: str, model: Optional[str] = None) -> str:
        """Generate response from Ollama model (legacy method)"""
        model = model or self.default_model
        
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("response", "")
            else:
                error_msg = f"Ollama API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)
                
        except httpx.TimeoutException:
            error_msg = "Request to Ollama timed out"
            logger.error(error_msg)
            raise Exception(error_msg)
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise
    
    async def generate_response_stream(self, prompt: str, model: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Generate streaming response from Ollama model"""
        model = model or self.default_model
        
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": True
            }
            
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload
            ) as response:
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                if "response" in data:
                                    yield data["response"]
                                if data.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                continue
                else:
                    error_msg = f"Ollama API error: {response.status_code}"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                    
        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            raise
    
    async def pull_model(self, model_name: str) -> bool:
        """Pull a model from Ollama registry"""
        try:
            payload = {"name": model_name}
            
            response = await self.client.post(
                f"{self.base_url}/api/pull",
                json=payload
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False

    def _create_image_prompt_from_request(self, message: str) -> Tuple[str, Optional[str]]:
        """Create a concise image prompt and detect style from user request"""
        message_lower = message.lower()
        
        # Detect style preferences from the request
        style = None
        if any(word in message_lower for word in ["realistic", "photorealistic", "real", "photo"]):
            style = "realistic"
        elif any(word in message_lower for word in ["cartoon", "stylized", "character"]):
            style = "semi_realistic"
        elif any(word in message_lower for word in ["artistic", "painting", "art", "beautiful"]):
            style = "artistic"
        elif any(word in message_lower for word in ["concept", "fantasy", "sci-fi", "cinematic"]):
            style = "concept_art"
        
        # Create concise prompts for common requests
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
            # Generic fallback - keep it short
            prompt = message.replace("show me", "").replace("draw", "").replace("create", "").replace("generate", "").strip()
            if not prompt or len(prompt) < 10:
                prompt = "Beautiful artistic illustration"
            elif len(prompt) > 200:  # Keep fallback prompts short
                prompt = prompt[:200].rsplit(' ', 1)[0] + "..."
        
        return prompt, style
    
    async def _chat_without_functions(
        self, 
        message: str, 
        model: str, 
        context: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        top_p: float = 0.9
    ) -> str:
        """Internal chat method without function calling to avoid recursion"""
        # Build conversation context
        messages = []
        if context:
            messages.extend(context)
        
        messages.append({"role": "user", "content": message})
        
        try:
            # Create the payload for chat completion
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "top_p": top_p
                }
            }
            
            # Call Ollama API directly
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("message", {}).get("content", "")
            else:
                logger.error(f"Ollama API error: {response.status_code}")
                return "Sorry, I encountered an error while processing your request."
                
        except Exception as e:
            logger.error(f"Ollama API error in _chat_without_functions: {e}")
            return "Sorry, I encountered an error while processing your request."
