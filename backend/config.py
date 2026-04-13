import os
import ipaddress
import base64
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Server Configuration
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 8000))
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"
    LAN_ONLY = os.getenv("LAN_ONLY", "False").lower() == "true"
    CLOUD_TEXT_ONLY = os.getenv("CLOUD_TEXT_ONLY", "False").lower() == "true"

    # AI Provider Configuration
    MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai").lower()
    ARCHIVE_ANALYSIS_PROVIDER = os.getenv("ARCHIVE_ANALYSIS_PROVIDER", "local").lower()

    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
    OPENAI_MODELS = [
        model.strip()
        for model in os.getenv("OPENAI_MODELS", "gpt-4.1,gpt-4.1-mini,gpt-4.1-nano").split(",")
        if model.strip()
    ]

    # Ollama Configuration
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    EMBEDDING_LOCAL_ONLY = os.getenv("EMBEDDING_LOCAL_ONLY", "False").lower() == "true"

    # Research vault configuration
    RESEARCH_VAULT_ENABLED = os.getenv("RESEARCH_VAULT_ENABLED", "True").lower() == "true"
    RESEARCH_VAULT_KEY = os.getenv("RESEARCH_VAULT_KEY")
    RESEARCH_VAULT_KEY_FILE = os.getenv("RESEARCH_VAULT_KEY_FILE", "./research_vault.key")
    
    # TTS Configuration
    TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    
    # Audio Configuration
    AUDIO_TEMP_DIR = os.getenv("AUDIO_TEMP_DIR", "./temp_audio")
    MAX_AUDIO_SIZE_MB = int(os.getenv("MAX_AUDIO_SIZE_MB", 25))

    # ComfyUI Configuration
    COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
    COMFYUI_FALLBACK_URLS = [
        url.strip()
        for url in os.getenv("COMFYUI_FALLBACK_URLS", "http://localhost:8188").split(",")
        if url.strip()
    ]
    
    # Conversation Storage
    CONVERSATION_STORAGE = os.getenv("CONVERSATION_STORAGE", "sqlite")
    DB_PATH = os.getenv("DB_PATH", "./conversations.db")
    
    # CORS Configuration
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:*,http://localhost:3001,http://127.0.0.1:*,http://127.0.0.1:3001").split(",")

    @staticmethod
    def is_lan_safe_url(url: str) -> bool:
        """Return True when the URL host stays on localhost or a private LAN."""
        if not url:
            return False

        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname in {"localhost"}:
            return True

        try:
            address = ipaddress.ip_address(hostname)
            return address.is_private or address.is_loopback or address.is_link_local
        except ValueError:
            return hostname.endswith(".local")
    
    @classmethod
    def validate_config(cls):
        """Validate configuration and return any errors"""
        errors = []

        if cls.MODEL_PROVIDER not in {"openai", "ollama"}:
            errors.append("MODEL_PROVIDER must be either 'openai' or 'ollama'")

        if cls.ARCHIVE_ANALYSIS_PROVIDER not in {"local", "openai"}:
            errors.append("ARCHIVE_ANALYSIS_PROVIDER must be either 'local' or 'openai'")

        if cls.MODEL_PROVIDER == "openai" and not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required when MODEL_PROVIDER is 'openai'")

        if cls.TTS_PROVIDER == "elevenlabs" and not cls.ELEVENLABS_API_KEY:
            errors.append("ELEVENLABS_API_KEY is required when TTS_PROVIDER is 'elevenlabs'")

        if not cls.COMFYUI_URL.startswith(("http://", "https://")):
            errors.append("COMFYUI_URL must start with http:// or https://")

        if cls.LAN_ONLY:
            if cls.TTS_PROVIDER != "pyttsx3":
                errors.append("TTS_PROVIDER must be 'pyttsx3' when LAN_ONLY is enabled")

            if cls.MODEL_PROVIDER == "openai" and not cls.is_lan_safe_url(cls.OPENAI_BASE_URL):
                errors.append("MODEL_PROVIDER=openai requires a LAN-safe OPENAI_BASE_URL when LAN_ONLY is enabled")

            if not cls.is_lan_safe_url(cls.OLLAMA_HOST):
                errors.append("OLLAMA_HOST must be LAN-safe when LAN_ONLY is enabled")

            if not cls.is_lan_safe_url(cls.COMFYUI_URL):
                errors.append("COMFYUI_URL must be LAN-safe when LAN_ONLY is enabled")

        if cls.RESEARCH_VAULT_ENABLED and cls.RESEARCH_VAULT_KEY:
            try:
                base64.urlsafe_b64decode(cls.RESEARCH_VAULT_KEY.encode("utf-8"))
            except Exception:
                errors.append("RESEARCH_VAULT_KEY must be a valid urlsafe base64 Fernet key")
            
        if not os.path.exists(cls.AUDIO_TEMP_DIR):
            try:
                os.makedirs(cls.AUDIO_TEMP_DIR, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create audio temp directory: {e}")
        
        return errors

config = Config()
