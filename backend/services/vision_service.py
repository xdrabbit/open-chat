import base64
import logging
from typing import Optional, Dict, Any, List
import httpx
from io import BytesIO
from PIL import Image
import os

from config import config

logger = logging.getLogger(__name__)

class VisionService:
    """Service for handling vision model interactions"""
    
    def __init__(self):
        self.ollama_url = config.OLLAMA_HOST
        self.vision_models = [
            "llava", "bakllava", "llava:latest", "bakllava:latest",
            "moondream", "cogvlm", "minicpm-v"
        ]
        
    async def get_available_vision_models(self) -> List[str]:
        """Get list of available vision models"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.ollama_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    available_models = [model["name"] for model in data.get("models", [])]
                    
                    # Filter for vision models
                    vision_models = [
                        model for model in available_models 
                        if any(vm in model.lower() for vm in self.vision_models)
                    ]
                    
                    logger.info(f"Available vision models: {vision_models}")
                    return vision_models
                else:
                    logger.error(f"Failed to get models: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting vision models: {e}")
            return []
    
    async def is_vision_model(self, model_name: str) -> bool:
        """Check if a model supports vision"""
        available_vision = await self.get_available_vision_models()
        return model_name in available_vision
    
    def encode_image(self, image_data: bytes) -> str:
        """Encode image data to base64"""
        try:
            # Optimize image if needed
            image = Image.open(BytesIO(image_data))
            
            # Resize if too large (max 1024px on longest side)
            max_size = 1024
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"Resized image to {new_size}")
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Save to bytes
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)
            
            # Encode to base64
            encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
            logger.info(f"Encoded image: {len(encoded)} characters")
            return encoded
            
        except Exception as e:
            logger.error(f"Error encoding image: {e}")
            raise
    
    async def analyze_image(
        self, 
        prompt: str, 
        image_data: bytes, 
        model: str = "bakllava:latest"
    ) -> str:
        """Analyze image with vision model"""
        try:
            # Check if model supports vision
            if not await self.is_vision_model(model):
                raise ValueError(f"Model {model} does not support vision")
            
            # Encode image
            encoded_image = self.encode_image(image_data)
            
            # Prepare request
            request_data = {
                "model": model,
                "prompt": prompt,
                "images": [encoded_image],
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_tokens": 2000
                }
            }
            
            logger.info(f"Analyzing image with {model}")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json=request_data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    analysis = result.get("response", "").strip()
                    
                    if analysis:
                        logger.info(f"Vision analysis completed: {len(analysis)} characters")
                        return analysis
                    else:
                        raise ValueError("Empty response from vision model")
                else:
                    error_text = response.text
                    logger.error(f"Vision model error: {response.status_code} - {error_text}")
                    raise ValueError(f"Vision model error: {error_text}")
                    
        except Exception as e:
            logger.error(f"Error analyzing image: {e}")
            raise
    
    async def chat_with_image(
        self, 
        message: str, 
        image_data: bytes, 
        model: str = "bakllava:latest",
        conversation_context: List[Dict[str, str]] = None
    ) -> str:
        """Have a conversation about an image"""
        try:
            # Build prompt with context
            if conversation_context:
                context_prompt = "\n".join([
                    f"{msg['role']}: {msg['content']}" 
                    for msg in conversation_context[-5:]  # Last 5 messages
                ])
                full_prompt = f"{context_prompt}\nuser: {message}"
            else:
                full_prompt = message
            
            return await self.analyze_image(full_prompt, image_data, model)
            
        except Exception as e:
            logger.error(f"Error in chat with image: {e}")
            raise
    
    def get_supported_formats(self) -> List[str]:
        """Get supported image formats"""
        return [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]
    
    def validate_image(self, image_data: bytes) -> bool:
        """Validate if the data is a valid image"""
        try:
            image = Image.open(BytesIO(image_data))
            image.verify()
            return True
        except Exception as e:
            logger.warning(f"Invalid image data: {e}")
            return False