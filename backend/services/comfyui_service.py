import asyncio
import json
import uuid
import logging
from typing import Dict, Any, List, Optional
import httpx
import base64
from io import BytesIO
from PIL import Image
import os
import time

from config import config
from .workflow_intelligence import WorkflowIntelligence, ModelSelector

logger = logging.getLogger(__name__)

class ComfyUIService:
    """Service for integrating with ComfyUI for image generation"""
    
    def __init__(self):
        self.base_urls = []
        for url in [config.COMFYUI_URL, *config.COMFYUI_FALLBACK_URLS]:
            normalized = url.rstrip("/")
            if normalized and normalized not in self.base_urls:
                self.base_urls.append(normalized)

        if not self.base_urls:
            self.base_urls = ["http://127.0.0.1:8188"]

        self.base_url = self.base_urls[0]
        self.client_id = str(uuid.uuid4())
        self._tested_url = False
        
    async def health_check(self) -> bool:
        """Check if ComfyUI is accessible with fast timeout and URL fallback"""
        if not self._tested_url:
            # Test URLs in order and use the first working one
            for url in self.base_urls:
                try:
                    async with httpx.AsyncClient(timeout=3.0) as client:  # Reasonable timeout
                        response = await client.get(f"{url}/system_stats")
                        if response.status_code == 200:
                            self.base_url = url
                            self._tested_url = True
                            logger.info(f"✅ ComfyUI connected at: {url}")
                            return True
                except Exception:
                    continue
            
            # No working URL found
            self._tested_url = True
            logger.warning("⚠️ ComfyUI not available at any endpoint")
            return False
        
        # Quick check if already tested
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/system_stats")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"ComfyUI health check failed: {e}")
            return False
    
    async def get_system_info(self) -> Dict[str, Any]:
        """Get ComfyUI system information"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/system_stats")
                if response.status_code == 200:
                    return response.json()
                return {}
        except Exception as e:
            logger.error(f"Failed to get ComfyUI system info: {e}")
            return {}
    
    async def get_models(self) -> List[str]:
        """Get available models in ComfyUI"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/object_info")
                if response.status_code == 200:
                    data = response.json()
                    # Extract checkpoint models
                    checkpoints = data.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [])
                    if isinstance(checkpoints, list) and len(checkpoints) > 0:
                        return checkpoints[0] if isinstance(checkpoints[0], list) else []
                return []
        except Exception as e:
            logger.error(f"Failed to get ComfyUI models: {e}")
            return []
    
    def create_text2img_workflow(self, prompt: str, negative_prompt: str = "", 
                                width: int = 1024, height: int = 1024, 
                                steps: int = 20, cfg: float = 8.0,
                                model: str = None) -> Dict[str, Any]:
        """Create a basic text-to-image workflow"""
        
        # Use a default model if none specified
        if not model:
            model = "RealVisXL_V5.0_fp16.safetensors"  # Based on your ComfyUI screenshot
        
        workflow = {
            "1": {
                "inputs": {
                    "ckpt_name": model
                },
                "class_type": "CheckpointLoaderSimple",
                "_meta": {"title": "Load Checkpoint"}
            },
            "2": {
                "inputs": {
                    "text": prompt,
                    "clip": ["1", 1]
                },
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "CLIP Text Encode (Prompt)"}
            },
            "3": {
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["1", 1]
                },
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "CLIP Text Encode (Negative)"}
            },
            "4": {
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                },
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "Empty Latent Image"}
            },
            "5": {
                "inputs": {
                    "seed": int(time.time()),  # Random seed based on current time
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
                },
                "class_type": "KSampler",
                "_meta": {"title": "KSampler"}
            },
            "6": {
                "inputs": {
                    "samples": ["5", 0],
                    "vae": ["1", 2]
                },
                "class_type": "VAEDecode",
                "_meta": {"title": "VAE Decode"}
            },
            "7": {
                "inputs": {
                    "filename_prefix": "OpenChat_generated",
                    "images": ["6", 0]
                },
                "class_type": "SaveImage",
                "_meta": {"title": "Save Image"}
            }
        }
        
        return workflow
    
    async def queue_prompt(self, workflow: Dict[str, Any]) -> str:
        """Queue a workflow for execution and return the prompt ID"""
        try:
            payload = {
                "prompt": workflow,
                "client_id": self.client_id
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/prompt",
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    prompt_id = result.get("prompt_id")
                    logger.info(f"Queued prompt with ID: {prompt_id}")
                    return prompt_id
                else:
                    logger.error(f"Failed to queue prompt: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error queuing prompt: {e}")
            return None
    
    async def wait_for_completion(self, prompt_id: str, timeout: int = 300) -> bool:
        """Wait for a prompt to complete execution"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self.base_url}/history/{prompt_id}")
                    
                    if response.status_code == 200:
                        history = response.json()
                        if prompt_id in history:
                            prompt_info = history[prompt_id]
                            status = prompt_info.get("status", {})
                            
                            if status.get("completed", False):
                                logger.info(f"Prompt {prompt_id} completed successfully")
                                return True
                            elif "error" in status:
                                logger.error(f"Prompt {prompt_id} failed: {status.get('error')}")
                                return False
                
                # Wait before checking again
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error checking prompt status: {e}")
                await asyncio.sleep(2)
        
        logger.error(f"Prompt {prompt_id} timed out after {timeout} seconds")
        return False
    
    async def get_generated_images(self, prompt_id: str) -> List[str]:
        """Get the generated image filenames for a completed prompt"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/history/{prompt_id}")
                
                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})
                        
                        image_files = []
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                for image_info in node_output["images"]:
                                    filename = image_info.get("filename")
                                    if filename:
                                        image_files.append(filename)
                        
                        logger.info(f"Found {len(image_files)} generated images for prompt {prompt_id}")
                        return image_files
                        
        except Exception as e:
            logger.error(f"Error getting generated images: {e}")
        
        return []
    
    async def download_image(self, filename: str, save_path: str) -> bool:
        """Download a generated image to local storage"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/view", params={"filename": filename})
                
                if response.status_code == 200:
                    with open(save_path, "wb") as f:
                        f.write(response.content)
                        f.flush()  # Ensure data is written to disk
                        os.fsync(f.fileno())  # Force OS to write to disk
                    
                    logger.info(f"Downloaded image: {filename} -> {save_path}")
                    return True
                else:
                    logger.error(f"Failed to download image {filename}: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error downloading image {filename}: {e}")
            return False
    
    async def generate_image(self, prompt: str, negative_prompt: str = "", 
                           width: int = 1024, height: int = 1024,
                           steps: int = 20, cfg: float = 8.0,
                           model: Optional[str] = None, style: Optional[str] = None) -> Optional[str]:
        """Generate an image using intelligent workflow selection"""
        try:
            logger.info(f"🎨 IMAGE GENERATION REQUEST:")
            logger.info(f"📝 Original Prompt: {prompt}")
            logger.info(f"🎭 Style: {style}")
            logger.info(f"📐 Dimensions: {width}x{height}")
            
            # Use intelligent workflow creation
            workflow_config = WorkflowIntelligence.create_intelligent_workflow(
                prompt=prompt, 
                style=style,
                user_params={
                    "width": width,
                    "height": height, 
                    "steps": steps,
                    "cfg": cfg
                } if model else None  # Only override if user provided specific params
            )
            
            # Use intelligent config unless user specified specific model
            final_model = model if model else workflow_config["model"]
            final_prompt = workflow_config["prompt"]
            
            logger.info(f"🔧 Enhanced Prompt: {final_prompt}")
            logger.info(f"🤖 Selected Model: {final_model}")
            logger.info(f"⚙️ Config: steps={workflow_config.get('steps', steps)}, cfg={workflow_config.get('cfg', cfg)}")
            final_negative = negative_prompt if negative_prompt else workflow_config["negative_prompt"]
            final_params = workflow_config["parameters"]
            
            logger.info(f"🧠 Intelligent generation - Model: {final_model}, Style: {workflow_config['style']}")
            
            # Create workflow with intelligent parameters
            workflow = self.create_text2img_workflow(
                prompt=final_prompt,
                negative_prompt=final_negative,
                width=final_params["width"],
                height=final_params["height"],
                steps=final_params["steps"],
                cfg=final_params["cfg"],
                model=final_model
            )
            
            # Queue the prompt
            prompt_id = await self.queue_prompt(workflow)
            if not prompt_id:
                return None
            
            # Wait for completion
            if not await self.wait_for_completion(prompt_id):
                return None
            
            # Get generated images
            image_files = await self.get_generated_images(prompt_id)
            if not image_files:
                return None
            
            # Download the first image
            remote_filename = image_files[0]
            local_filename = f"comfyui_{prompt_id}_{remote_filename}"
            local_path = os.path.join(config.AUDIO_TEMP_DIR, local_filename)
            
            if await self.download_image(remote_filename, local_path):
                logger.info(f"✅ Generated image with {workflow_config['style']} style: {local_filename}")
                return local_filename
            
            return None
            
        except Exception as e:
            logger.error(f"Error in intelligent generate_image: {e}")
            return None
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/queue")
                if response.status_code == 200:
                    return response.json()
                return {}
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {}

    def get_active_url(self) -> str:
        """Return the current ComfyUI endpoint."""
        return self.base_url
