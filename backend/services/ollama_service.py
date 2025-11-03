import httpx
import json
import logging
from typing import Optional, AsyncGenerator
from config import config

logger = logging.getLogger(__name__)

class OllamaService:
    """Service for communicating with Ollama API"""
    
    def __init__(self):
        self.base_url = config.OLLAMA_HOST
        self.default_model = config.OLLAMA_MODEL
        
    async def health_check(self) -> bool:
        """Check if Ollama is running and accessible"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False
    
    async def get_available_models(self) -> list:
        """Get list of available models from Ollama"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return [model["name"] for model in data.get("models", [])]
                return []
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []
    
    async def generate_response(self, prompt: str, model: Optional[str] = None) -> str:
        """Generate response from Ollama model"""
        model = model or self.default_model
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                }
                
                response = await client.post(
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
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": True
                }
                
                async with client.stream(
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
            async with httpx.AsyncClient(timeout=300.0) as client:
                payload = {"name": model_name}
                
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json=payload
                )
                
                return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False