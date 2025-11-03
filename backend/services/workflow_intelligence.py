"""
Intelligent Workflow and Model Selection for ComfyUI
Enhanced AI-Initiated Image Generation with Smart Model Choosing
Claude - November 3, 2025
"""

import logging
import re
from typing import Dict, Tuple, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class ImageStyle(Enum):
    """Available image styles"""
    REALISTIC = "realistic"
    SEMI_REALISTIC = "semi_realistic" 
    ARTISTIC = "artistic"
    CONCEPT_ART = "concept_art"
    DETAILED = "detailed"
    QUICK = "quick"

class ModelSelector:
    """Intelligent model selection based on user requests and style preferences"""
    
    # Available models with their strengths
    MODELS = {
        "realistic": "RealVisXL_V5.0_fp16.safetensors",
        "semi_realistic": "realcartoonXL_v7.safetensors", 
        "artistic": "dreamshaperXL_v21TurboDPMSDE.safetensors",
        "very_realistic": "jedpointreal_v1ILVae.safetensors",
        "concept_art": "ConceptArtXL.safetensors",  # When loaded
        "default": "RealVisXL_V5.0_fp16.safetensors"
    }
    
    # Style keywords that indicate preferred rendering approach
    STYLE_KEYWORDS = {
        "realistic": [
            "photorealistic", "real", "photography", "photo", "lifelike", 
            "actual", "true to life", "documentary", "portrait", "headshot"
        ],
        "very_realistic": [
            "hyperrealistic", "ultra realistic", "extremely realistic", 
            "photographic quality", "camera quality", "professional photo"
        ],
        "semi_realistic": [
            "cartoon", "stylized", "illustrated", "character design",
            "animated", "semi-realistic", "cartoon style", "character art"
        ],
        "artistic": [
            "artistic", "painting", "art", "drawn", "sketch", "creative",
            "stylistic", "painterly", "illustration", "artwork", "beautiful"
        ],
        "concept_art": [
            "concept", "fantasy", "sci-fi", "science fiction", "futuristic",
            "otherworldly", "magical", "epic", "dramatic", "cinematic"
        ]
    }
    
    # Content type keywords for parameter optimization
    CONTENT_KEYWORDS = {
        "portrait": ["portrait", "face", "person", "character", "headshot", "bust"],
        "landscape": ["landscape", "scenery", "environment", "vista", "panorama"],
        "detailed": ["detailed", "intricate", "complex", "elaborate", "fine"],
        "simple": ["simple", "clean", "minimal", "basic", "quick"]
    }

    @classmethod
    def analyze_style_preference(cls, prompt: str, user_style: Optional[str] = None) -> str:
        """Analyze prompt to determine best style/model"""
        prompt_lower = prompt.lower()
        
        # If user explicitly specified style, prioritize that
        if user_style and user_style.lower() in cls.MODELS:
            logger.info(f"Using user-specified style: {user_style}")
            return user_style.lower()
        
        # Score each style based on keyword matches
        style_scores = {}
        for style, keywords in cls.STYLE_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in prompt_lower)
            if score > 0:
                style_scores[style] = score
        
        # Choose style with highest score
        if style_scores:
            best_style = max(style_scores, key=style_scores.get)
            logger.info(f"Detected style '{best_style}' with score {style_scores[best_style]} from prompt analysis")
            return best_style
        
        # Default fallback based on general content
        if any(word in prompt_lower for word in ["photo", "real", "actual"]):
            return "realistic"
        elif any(word in prompt_lower for word in ["art", "painting", "beautiful"]):
            return "artistic"
        else:
            logger.info("No specific style detected, using default realistic model")
            return "realistic"

    @classmethod
    def get_optimal_model(cls, prompt: str, style: Optional[str] = None) -> str:
        """Get the best model for the given prompt and style"""
        detected_style = cls.analyze_style_preference(prompt, style)
        model = cls.MODELS.get(detected_style, cls.MODELS["default"])
        
        logger.info(f"Selected model: {model} for style: {detected_style}")
        return model

    @classmethod
    def get_optimal_parameters(cls, prompt: str, style: Optional[str] = None) -> Dict:
        """Get optimal generation parameters based on prompt content"""
        prompt_lower = prompt.lower()
        detected_style = cls.analyze_style_preference(prompt, style)
        
        # Base parameters
        params = {
            "steps": 30,
            "cfg": 7.5,
            "width": 1024,
            "height": 1024
        }
        
        # Adjust based on content type
        if any(word in prompt_lower for word in cls.CONTENT_KEYWORDS["detailed"]):
            params.update({"steps": 40, "cfg": 9.0})
            logger.info("Using detailed parameters: higher steps and CFG")
        elif any(word in prompt_lower for word in cls.CONTENT_KEYWORDS["simple"]):
            params.update({"steps": 20, "cfg": 6.0})
            logger.info("Using quick parameters: lower steps and CFG")
        
        # Adjust based on aspect ratio hints
        if any(word in prompt_lower for word in cls.CONTENT_KEYWORDS["portrait"]):
            params.update({"width": 768, "height": 1024})
            logger.info("Using portrait aspect ratio")
        elif any(word in prompt_lower for word in cls.CONTENT_KEYWORDS["landscape"]):
            params.update({"width": 1024, "height": 768})
            logger.info("Using landscape aspect ratio")
        
        # Style-specific adjustments
        if detected_style == "very_realistic":
            params.update({"steps": 35, "cfg": 8.0})
            logger.info("Enhanced parameters for very realistic style")
        elif detected_style == "artistic":
            params.update({"cfg": 8.5})
            logger.info("Higher CFG for artistic style")
        elif detected_style == "concept_art":
            params.update({"steps": 35, "cfg": 9.0})
            logger.info("Enhanced parameters for concept art")
        
        return params

class WorkflowIntelligence:
    """Enhanced workflow selection and optimization"""
    
    @staticmethod
    def enhance_prompt_for_style(prompt: str, style: str) -> str:
        """Enhance the prompt based on selected style"""
        style_enhancements = {
            "realistic": "photorealistic, detailed, high quality",
            "very_realistic": "hyperrealistic, ultra detailed, professional photography quality",
            "semi_realistic": "stylized, character design, illustrated, clean art style",
            "artistic": "artistic, beautiful composition, painterly style, masterpiece",
            "concept_art": "concept art, cinematic, dramatic lighting, epic composition"
        }
        
        enhancement = style_enhancements.get(style, "high quality, detailed")
        enhanced = f"{prompt}, {enhancement}"
        
        logger.info(f"Enhanced prompt for {style} style: {enhanced}")
        return enhanced
    
    @staticmethod
    def get_negative_prompt_for_style(style: str) -> str:
        """Get optimized negative prompt based on style"""
        base_negative = "blurry, low quality, distorted, ugly, bad anatomy"
        
        style_negatives = {
            "realistic": f"{base_negative}, cartoon, anime, painting, artistic",
            "very_realistic": f"{base_negative}, stylized, cartoon, anime, painting, unrealistic",
            "semi_realistic": f"{base_negative}, too realistic, photographic, overly detailed",
            "artistic": f"{base_negative}, photographic, too realistic, mundane",
            "concept_art": f"{base_negative}, mundane, boring, simple, low effort"
        }
        
        return style_negatives.get(style, base_negative)
    
    @staticmethod
    def create_intelligent_workflow(prompt: str, style: Optional[str] = None, 
                                  user_params: Optional[Dict] = None) -> Dict:
        """Create an optimized workflow based on intelligent analysis"""
        
        # Get optimal model and parameters
        model = ModelSelector.get_optimal_model(prompt, style)
        params = ModelSelector.get_optimal_parameters(prompt, style)
        
        # Override with user parameters if provided
        if user_params:
            params.update(user_params)
        
        # Enhance prompt and get negative prompt
        detected_style = ModelSelector.analyze_style_preference(prompt, style)
        enhanced_prompt = WorkflowIntelligence.enhance_prompt_for_style(prompt, detected_style)
        negative_prompt = WorkflowIntelligence.get_negative_prompt_for_style(detected_style)
        
        workflow_config = {
            "model": model,
            "prompt": enhanced_prompt,
            "negative_prompt": negative_prompt,
            "style": detected_style,
            "parameters": params
        }
        
        logger.info(f"Created intelligent workflow: {workflow_config}")
        return workflow_config

# Example usage and testing
if __name__ == "__main__":
    # Test cases
    test_prompts = [
        "show me a beautiful sunset over mountains",
        "draw a realistic portrait of a person",
        "create a hyperrealistic photo of a city",
        "visualize a cartoon character design", 
        "illustrate a fantasy concept art scene",
        "generate a detailed architectural blueprint"
    ]
    
    print("🧠 Testing Intelligent Model Selection:")
    print("=" * 50)
    
    for prompt in test_prompts:
        print(f"\nPrompt: {prompt}")
        workflow = WorkflowIntelligence.create_intelligent_workflow(prompt)
        print(f"Model: {workflow['model']}")
        print(f"Style: {workflow['style']}")
        print(f"Parameters: {workflow['parameters']}")
        print(f"Enhanced Prompt: {workflow['prompt'][:80]}...")