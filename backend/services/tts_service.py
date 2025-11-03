import os
import asyncio
import tempfile
import logging
from abc import ABC, abstractmethod
from typing import Optional
import uuid
from datetime import datetime

from config import config

logger = logging.getLogger(__name__)

class BaseTTSProvider(ABC):
    """Abstract base class for TTS providers"""
    
    @abstractmethod
    async def generate_speech(self, text: str, voice_id: Optional[str] = None) -> str:
        """Generate speech and return filename"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available"""
        pass

class ElevenLabsTTSProvider(BaseTTSProvider):
    """ElevenLabs TTS provider"""
    
    def __init__(self):
        self.api_key = config.ELEVENLABS_API_KEY
        self.default_voice_id = config.ELEVENLABS_VOICE_ID
        
    async def generate_speech(self, text: str, voice_id: Optional[str] = None) -> str:
        """Generate speech using ElevenLabs API"""
        try:
            # Import here to avoid dependency issues if not using ElevenLabs
            from elevenlabs.client import ElevenLabs
            
            voice_id = voice_id or self.default_voice_id
            
            # Generate audio
            client = ElevenLabs(api_key=self.api_key)
            audio = client.generate(
                text=text,
                voice=voice_id,
                model="eleven_monolingual_v1"
            )
            
            # Save to temporary file
            filename = f"tts_{uuid.uuid4().hex}_{int(datetime.now().timestamp())}.mp3"
            file_path = os.path.join(config.AUDIO_TEMP_DIR, filename)
            
            # Write audio data to file
            with open(file_path, "wb") as f:
                for chunk in audio:
                    f.write(chunk)
            
            logger.info(f"Generated ElevenLabs TTS: {filename}")
            return filename
            
        except ImportError:
            raise Exception("ElevenLabs library not installed")
        except Exception as e:
            logger.error(f"ElevenLabs TTS error: {e}")
            raise Exception(f"Failed to generate speech with ElevenLabs: {str(e)}")
    
    def is_available(self) -> bool:
        """Check if ElevenLabs is available"""
        try:
            from elevenlabs.client import ElevenLabs
            return bool(self.api_key)
        except ImportError:
            return False

class PyttsTTSProvider(BaseTTSProvider):
    """Local TTS provider using pyttsx3"""
    
    def __init__(self):
        self.engine = None
        self._initialize_engine()
    
    def _initialize_engine(self):
        """Initialize pyttsx3 engine"""
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            
            # Configure voice settings
            voices = self.engine.getProperty('voices')
            if voices:
                # Try to find a good default voice
                for voice in voices:
                    if 'en' in voice.id.lower() or 'english' in voice.name.lower():
                        self.engine.setProperty('voice', voice.id)
                        break
            
            # Set speaking rate and volume
            self.engine.setProperty('rate', 150)  # Speed of speech
            self.engine.setProperty('volume', 1.0)  # Volume level (0.0 to 1.0)
            
            logger.info("✅ pyttsx3 TTS engine initialized")
            
        except ImportError:
            logger.error("pyttsx3 not installed")
            self.engine = None
        except Exception as e:
            logger.error(f"Failed to initialize pyttsx3: {e}")
            self.engine = None
    
    async def generate_speech(self, text: str, voice_id: Optional[str] = None) -> str:
        """Generate speech using pyttsx3"""
        if not self.engine:
            raise Exception("pyttsx3 engine not available")
        
        try:
            # Generate unique filename
            filename = f"tts_{uuid.uuid4().hex}_{int(datetime.now().timestamp())}.wav"
            file_path = os.path.join(config.AUDIO_TEMP_DIR, filename)
            
            # Run TTS in executor to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._generate_sync, text, file_path)
            
            logger.info(f"Generated pyttsx3 TTS: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"pyttsx3 TTS error: {e}")
            raise Exception(f"Failed to generate speech with pyttsx3: {str(e)}")
    
    def _generate_sync(self, text: str, file_path: str):
        """Synchronous TTS generation"""
        try:
            self.engine.save_to_file(text, file_path)
            self.engine.runAndWait()
        except Exception as e:
            logger.error(f"pyttsx3 sync generation error: {e}")
            raise
    
    def is_available(self) -> bool:
        """Check if pyttsx3 is available"""
        return self.engine is not None

class TTSService:
    """Main TTS service with configurable providers"""
    
    def __init__(self):
        self.providers = {
            "elevenlabs": ElevenLabsTTSProvider(),
            "pyttsx3": PyttsTTSProvider()
        }
        self.current_provider = config.TTS_PROVIDER
        self._validate_provider()
    
    def _validate_provider(self):
        """Validate and set fallback provider if needed"""
        if self.current_provider not in self.providers:
            logger.warning(f"Invalid TTS provider: {self.current_provider}")
            self.current_provider = "pyttsx3"  # fallback
        
        provider = self.providers[self.current_provider]
        if not provider.is_available():
            logger.warning(f"TTS provider {self.current_provider} not available, trying fallback")
            
            # Try fallback providers
            for name, fallback_provider in self.providers.items():
                if name != self.current_provider and fallback_provider.is_available():
                    self.current_provider = name
                    logger.info(f"Using fallback TTS provider: {name}")
                    break
            else:
                logger.error("No TTS providers available")
    
    async def generate_speech(self, text: str, voice_id: Optional[str] = None) -> str:
        """Generate speech using current provider"""
        if not text.strip():
            raise Exception("No text provided for TTS")
        
        provider = self.providers.get(self.current_provider)
        if not provider:
            raise Exception(f"TTS provider {self.current_provider} not found")
        
        if not provider.is_available():
            raise Exception(f"TTS provider {self.current_provider} not available")
        
        return await provider.generate_speech(text, voice_id)
    
    def switch_provider(self, provider_name: str) -> bool:
        """Switch to a different TTS provider"""
        if provider_name not in self.providers:
            logger.error(f"Unknown TTS provider: {provider_name}")
            return False
        
        provider = self.providers[provider_name]
        if not provider.is_available():
            logger.error(f"TTS provider {provider_name} not available")
            return False
        
        self.current_provider = provider_name
        logger.info(f"Switched to TTS provider: {provider_name}")
        return True
    
    def get_current_provider(self) -> str:
        """Get current provider name"""
        return self.current_provider
    
    def get_available_providers(self) -> list:
        """Get list of available providers"""
        return [
            name for name, provider in self.providers.items()
            if provider.is_available()
        ]
    
    def is_available(self) -> bool:
        """Check if any TTS provider is available"""
        return any(provider.is_available() for provider in self.providers.values())