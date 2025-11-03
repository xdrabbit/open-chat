import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Server Configuration
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 8000))
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"
    
    # Ollama Configuration
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
    
    # TTS Configuration
    TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    
    # Audio Configuration
    AUDIO_TEMP_DIR = os.getenv("AUDIO_TEMP_DIR", "./temp_audio")
    MAX_AUDIO_SIZE_MB = int(os.getenv("MAX_AUDIO_SIZE_MB", 25))
    
    # Conversation Storage
    CONVERSATION_STORAGE = os.getenv("CONVERSATION_STORAGE", "sqlite")
    DB_PATH = os.getenv("DB_PATH", "./conversations.db")
    
    # CORS Configuration
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:*").split(",")
    
    @classmethod
    def validate_config(cls):
        """Validate configuration and return any errors"""
        errors = []
        
        if cls.TTS_PROVIDER == "elevenlabs" and not cls.ELEVENLABS_API_KEY:
            errors.append("ELEVENLABS_API_KEY is required when TTS_PROVIDER is 'elevenlabs'")
            
        if not os.path.exists(cls.AUDIO_TEMP_DIR):
            try:
                os.makedirs(cls.AUDIO_TEMP_DIR, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create audio temp directory: {e}")
        
        return errors

config = Config()