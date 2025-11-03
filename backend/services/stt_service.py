import whisper
import tempfile
import os
import logging
from typing import Optional
from config import config

logger = logging.getLogger(__name__)

class STTService:
    """Speech-to-Text service using OpenAI Whisper"""
    
    def __init__(self):
        self.model = None
        self.model_name = "base"  # Options: tiny, base, small, medium, large
        self._load_model()
    
    def _load_model(self):
        """Load Whisper model lazily"""
        try:
            if self.model is None:
                logger.info(f"Loading Whisper model: {self.model_name}")
                self.model = whisper.load_model(self.model_name)
                logger.info("✅ Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            self.model = None
    
    async def transcribe(self, audio_data: bytes, filename: Optional[str] = None) -> str:
        """Transcribe audio data to text"""
        if self.model is None:
            self._load_model()
            if self.model is None:
                raise Exception("Whisper model not available")
        
        # Create temporary file for audio data
        temp_file_path = None
        try:
            # Determine file extension
            ext = ".wav"  # default
            if filename:
                _, ext = os.path.splitext(filename)
                if not ext:
                    ext = ".wav"
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(
                delete=False, 
                suffix=ext,
                dir=config.AUDIO_TEMP_DIR
            ) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            # Transcribe audio
            logger.info(f"Transcribing audio file: {temp_file_path}")
            result = self.model.transcribe(temp_file_path)
            
            text = result.get("text", "").strip()
            logger.info(f"Transcription result: {text[:100]}...")
            
            return text
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            raise Exception(f"Failed to transcribe audio: {str(e)}")
        
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_file_path}: {e}")
    
    def get_supported_languages(self) -> list:
        """Get list of supported languages"""
        return [
            "en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh",
            "ar", "hi", "tr", "pl", "nl", "sv", "da", "no", "fi"
        ]
    
    def change_model(self, model_name: str):
        """Change Whisper model"""
        valid_models = ["tiny", "base", "small", "medium", "large"]
        if model_name in valid_models:
            self.model_name = model_name
            self.model = None  # Force reload
            logger.info(f"Changed Whisper model to: {model_name}")
        else:
            logger.warning(f"Invalid model name: {model_name}. Valid options: {valid_models}")
    
    def is_available(self) -> bool:
        """Check if STT service is available"""
        return self.model is not None