# Open Chat - Voice Assistant with OpenAI or Ollama

A self-contained web application that enables real-time conversational interaction with OpenAI or Ollama models using both voice and text. The default configuration now uses OpenAI's `gpt-4.1` family. It includes offline speech recognition, configurable text-to-speech, and a clean web interface.

## 🚀 Features

- **Voice & Text Chat**: Speak or type to interact with AI models
- **Local Speech Recognition**: Uses OpenAI Whisper for offline speech-to-text
- **Configurable TTS**: Supports ElevenLabs (cloud) or pyttsx3 (local) text-to-speech
- **Real-time Conversation**: Fluid chat experience with audio playback
- **Conversation History**: SQLite-backed message storage with retrieval
- **Model Selection**: Choose from available OpenAI or Ollama models
- **Responsive UI**: Clean, modern interface that works on desktop and mobile
- **Fully Offline Capable**: Can operate without internet (except for ElevenLabs TTS)

## 📋 Prerequisites

### Required Software
- **Python 3.8+** with pip
- **OpenAI API key** for the default setup, or Ollama for a fully local setup
- **Node.js** (optional, for development)

### OpenAI Setup (Default)
1. Create an OpenAI API key
2. Copy `.env.example` to `.env`
3. Set:
   ```env
   MODEL_PROVIDER=openai
   OPENAI_API_KEY=your_key_here
   OPENAI_MODEL=gpt-4.1
   ```

### Ollama Setup (Optional)
1. Install Ollama from [ollama.ai](https://ollama.ai)
2. Start Ollama service:
   ```bash
   ollama serve
   ```
3. Download a model:
   ```bash
   ollama pull llama3.2
   # or other models: llama3, mistral, codellama, etc.
   ```

## 🛠️ Installation

### Quick Start
```bash
# Clone or download the project
cd open-chat

# Run the startup script (recommended)
./start.sh
```

### Manual Installation
```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Copy and edit configuration
cp .env.example .env
# Edit .env with your settings

# 4. Create audio directory
mkdir -p temp_audio

# 5. Start the application
cd backend
python main.py
```

## ⚙️ Configuration

Edit the `.env` file to customize your setup:

### Server Settings
```env
HOST=0.0.0.0                    # Server host (0.0.0.0 for all interfaces)
PORT=8282                       # Server port
DEBUG=True                      # Enable debug mode
CORS_ORIGINS=http://192.168.0.12:*,http://localhost:*  # Allowed origins
```

### AI Provider Settings
```env
LAN_ONLY=False                   # Set True to block cloud TTS/OpenAI usage
CLOUD_TEXT_ONLY=False            # When True, remote OpenAI only receives live chat text
MODEL_PROVIDER=openai              # Options: openai, ollama
ARCHIVE_ANALYSIS_PROVIDER=local    # Keep raw-file parsing/distillation local by default
OPENAI_API_KEY=your_key_here       # Required when MODEL_PROVIDER=openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1               # Default OpenAI model
OPENAI_MODELS=gpt-4.1,gpt-4.1-mini,gpt-4.1-nano
```

### Ollama Settings
```env
OLLAMA_HOST=http://localhost:11434  # Ollama API endpoint
OLLAMA_MODEL=llama3.2               # Default model name
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_LOCAL_ONLY=False          # Set True to prevent Hugging Face fetches
```

### Research Vault
```env
RESEARCH_VAULT_ENABLED=True
RESEARCH_VAULT_KEY=
RESEARCH_VAULT_KEY_FILE=./research_vault.key
```
The research vault is encrypted at rest, append-only through the app, and has no cleartext read endpoint. The app exposes only aggregate stats and a full wipe operation.

### TTS Configuration
```env
TTS_PROVIDER=pyttsx3                # Options: elevenlabs, pyttsx3
ELEVENLABS_API_KEY=your_key_here    # Required for ElevenLabs
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # ElevenLabs voice
```

### Hard LAN-Only Mode
```env
LAN_ONLY=True
MODEL_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b
TTS_PROVIDER=pyttsx3
EMBEDDING_LOCAL_ONLY=True
COMFYUI_URL=http://192.168.0.40:8188
```

### Local Parsing + OpenAI Chat Only
```env
CLOUD_TEXT_ONLY=True
ARCHIVE_ANALYSIS_PROVIDER=local
MODEL_PROVIDER=openai
TTS_PROVIDER=pyttsx3
EMBEDDING_LOCAL_ONLY=True
```

### Audio Settings
```env
AUDIO_TEMP_DIR=./temp_audio     # Temporary audio storage
MAX_AUDIO_SIZE_MB=25            # Max upload size
```

### Local ComfyUI Settings
```env
COMFYUI_URL=http://127.0.0.1:8188
COMFYUI_FALLBACK_URLS=http://localhost:8188
```

### Storage Settings
```env
CONVERSATION_STORAGE=sqlite     # Options: sqlite, memory
DB_PATH=./conversations.db      # SQLite database path
```

## 🎯 Usage

### Starting the Application
1. Ensure your configured model provider is ready
2. Start Open Chat:
   ```bash
   ./start.sh
   ```
3. Open your browser to `http://localhost:8282`

### Cross-Network Access
To access from another device (like Mac Mini → WSL):
1. Update `.env` with your IP addresses:
   ```env
   HOST=0.0.0.0
   CORS_ORIGINS=http://192.168.0.12:*,http://192.168.0.45:*
   ```
2. Access from client: `http://192.168.0.45:8282`

### Using the Interface
- **Text Chat**: Type in the input field and press Enter or click Send
- **Voice Chat**: Click the microphone button, speak, then click again to stop
- **Audio Playback**: Assistant responses automatically play audio (if TTS enabled)
- **Model Selection**: Choose different OpenAI or Ollama models from the dropdown
- **TTS Provider**: Switch between ElevenLabs and local TTS
- **Local Drawing**: Ask the chat to "draw", "paint", "sketch", or "render" something and it will use your local ComfyUI image generator

## 🏗️ Architecture

### Backend (FastAPI)
- **`main.py`**: Main application and API endpoints
- **`config.py`**: Configuration management
- **`services/`**: Core service modules
  - `ollama_service.py`: Ollama API integration
  - `stt_service.py`: Speech-to-text using Whisper
  - `tts_service.py`: Configurable text-to-speech
  - `conversation_service.py`: Message storage and retrieval

### Frontend (HTML/JS)
- **`index.html`**: Clean, responsive chat interface
- **`chat.js`**: JavaScript for real-time interaction

### API Endpoints
- `GET /`: Serve frontend interface
- `GET /health`: System health check
- `POST /chat`: Send message to AI model
- `POST /transcribe`: Convert audio to text
- `POST /speak`: Convert text to audio
- `GET /audio/{filename}`: Serve audio files
- `GET /conversations`: Get chat history

## 🔧 Development

### Project Structure
```
open-chat/
├── backend/
│   ├── main.py                 # FastAPI application
│   ├── config.py              # Configuration
│   ├── models/
│   │   └── schemas.py         # Pydantic models
│   └── services/
│       ├── ollama_service.py  # Ollama integration
│       ├── stt_service.py     # Speech recognition
│       ├── tts_service.py     # Text-to-speech
│       └── conversation_service.py  # Chat storage
├── frontend/
│   ├── index.html             # Web interface
│   └── chat.js               # Frontend logic
├── temp_audio/               # Audio file storage
├── requirements.txt          # Python dependencies
├── .env                     # Configuration
└── start.sh                 # Startup script
```

### Adding New TTS Providers
1. Create a new class inheriting from `BaseTTSProvider` in `tts_service.py`
2. Implement `generate_speech()` and `is_available()` methods
3. Add to the `providers` dictionary in `TTSService`
4. Update configuration options

### Future RAG Extension
The architecture is designed for easy RAG integration:
- Add document processing service
- Implement vector search capabilities
- Extend conversation context with retrieved documents

## 🐛 Troubleshooting

### Common Issues

**"Ollama connection failed"**
- Ensure Ollama is running: `ollama serve`
- Check if a model is available: `ollama list`
- Verify Ollama URL in `.env`

**"Microphone access denied"**
- Enable microphone permissions in browser
- Use HTTPS for production deployment
- Check browser compatibility (modern browsers required)

**"TTS generation failed"**
- For ElevenLabs: Check API key and internet connection
- For pyttsx3: Ensure system TTS is available
- Try switching TTS provider in settings

**"Audio playback issues"**
- Check browser audio permissions
- Verify audio files in `temp_audio/` directory
- Try different audio format if needed

### Performance Optimization
- Use smaller Whisper models (`tiny`, `base`) for faster transcription
- Enable GPU acceleration for Ollama models
- Adjust audio quality settings for bandwidth constraints

### Security Notes
- The application binds to `0.0.0.0` by default for cross-network access
- For production, use HTTPS and proper authentication
- Audio files are temporarily stored and should be cleaned periodically

## 📝 License

This project is designed for educational and personal use. Please respect the licenses of the included dependencies:
- Ollama: [License](https://ollama.ai)
- OpenAI Whisper: MIT License
- ElevenLabs: Check their terms of service
- FastAPI: MIT License

## 🤝 Contributing

This is a modular architecture designed for extension:
1. Fork the repository
2. Create feature branches
3. Add comprehensive tests
4. Submit pull requests

## 📞 Support

For issues and questions:
1. Check the troubleshooting section
2. Review Ollama and dependency documentation
3. Verify your environment configuration

---

**Acceptance Test Checklist:**
- [ ] User can type messages and receive AI responses
- [ ] User can speak via microphone and receive transcribed text
- [ ] AI responses are played as audio automatically
- [ ] Conversation history is preserved
- [ ] No cloud connection required (with local TTS)
- [ ] Interface is responsive and handles errors gracefully
- [ ] Cross-network access works (WSL ↔ Mac)
