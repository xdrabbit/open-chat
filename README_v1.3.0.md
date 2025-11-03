# 🎨 Open Chat v1.3.0 - Complete Multimodal AI Assistant

A professional, local AI assistant with comprehensive multimodal capabilities including text, voice, vision, document RAG, and AI image generation.

![Open Chat Screenshot](https://img.shields.io/badge/Status-Production%20Ready-brightgreen) ![Version](https://img.shields.io/badge/Version-1.3.0-blue) ![Python](https://img.shields.io/badge/Python-3.8+-orange) ![License](https://img.shields.io/badge/License-MIT-green)

## 🌟 Features

### 💬 **Text Chat**
- Advanced conversation with Ollama LLMs (llama3.2, etc.)
- Intelligent context awareness and conversation history
- Real-time response streaming

### 🔊 **Voice Integration**
- **Speech-to-Text**: OpenAI Whisper for accurate voice recognition
- **Text-to-Speech**: ElevenLabs premium voices or local pyttsx3
- Enhanced audio controls (play/pause/stop/restart)

### 👁️ **Vision Analysis**
- **Multi-modal AI**: bakllava and llava vision models
- **Image Upload**: Drag-drop or camera button with preview
- **Format Support**: .jpg, .png, .gif, .bmp, .webp
- Automatic vision model detection and switching

### 📚 **RAG Knowledge Base**
- **Document Processing**: .txt, .md, .pdf, .docx support
- **Vector Embeddings**: sentence-transformers with CUDA acceleration
- **Drag & Drop**: Easy document upload with progress tracking
- **Smart Retrieval**: Context-aware document search

### 🎨 **AI Image Generation**
- **ComfyUI Integration**: Professional image generation workflows
- **Real-time Progress**: Live generation tracking with status updates
- **Parameter Control**: Width, height, steps, CFG, negative prompts
- **Gallery Display**: Generated images with download functionality
- **GPU Acceleration**: NVIDIA RTX support with cross-network capability

### 🖥️ **Professional Interface**
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Real-time Status**: Service health monitoring for all components
- **Conversation Management**: History, stats, and clear functionality
- **Modern UI**: Glassmorphism design with smooth animations

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Open Chat v1.3.0                        │
├─────────────────────────────────────────────────────────────┤
│  Frontend (Modern Web Interface)                           │
│  ├── Responsive Chat UI with multimodal controls           │
│  ├── Real-time status monitoring                           │
│  ├── Drag-drop file uploads                                │
│  └── Professional image generation interface               │
├─────────────────────────────────────────────────────────────┤
│  Backend (FastAPI + Microservices)                         │
│  ├── Ollama Service (Text + Vision LLMs)                   │
│  ├── STT Service (Whisper)                                 │
│  ├── TTS Service (ElevenLabs + pyttsx3)                    │
│  ├── RAG Service (sentence-transformers + SQLite)          │
│  ├── Vision Service (bakllava/llava integration)           │
│  ├── ComfyUI Service (Image generation workflows)          │
│  └── Conversation Service (SQLite + history management)    │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure                                            │
│  ├── Local: Ollama (11434), Backend (8000)                │
│  ├── Remote: ComfyUI GPU Server (configurable)            │
│  └── Storage: SQLite + Vector DB + File uploads           │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- **Python 3.8+** with pip
- **Ollama** with models: `ollama pull llama3.2:latest bakllava:latest llava:latest`
- **ComfyUI Server** (optional, for image generation)
- **ElevenLabs API Key** (optional, for premium TTS)

### Installation
```bash
# Clone the repository
git clone https://github.com/xdrabbit/open-chat.git
cd open-chat

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys and preferences

# Start the application
./start.sh
```

### 🌐 Access
Open your browser to: **http://localhost:8000**

## ⚙️ Configuration

### Environment Variables (`.env`)
```bash
# API Keys
ELEVENLABS_API_KEY=your_key_here

# Model Configuration
DEFAULT_MODEL=llama3.2:latest
DEFAULT_VISION_MODEL=bakllava:latest

# Service Providers
TTS_PROVIDER=elevenlabs  # or 'pyttsx3' for local
STT_PROVIDER=whisper

# ComfyUI Integration
COMFYUI_HOST=192.168.0.45  # Your ComfyUI server IP
COMFYUI_PORT=8188

# Server Configuration
HOST=0.0.0.0
PORT=8000
```

### ComfyUI Setup (Optional)
For AI image generation, set up ComfyUI on a GPU-enabled machine:
1. Install ComfyUI: https://github.com/comfyanonymous/ComfyUI
2. Download RealVisXL_V5.0_fp16.safetensors model
3. Configure COMFYUI_HOST in .env
4. Ensure port 8188 is accessible

## 🏃‍♂️ Running the Application

### Development Mode
```bash
# Start backend
cd backend
source ../venv/bin/activate
python main.py

# Access at http://localhost:8000
```

### Production Mode
```bash
# Use the provided start script
./start.sh
```

### Service Health Check
```bash
# Check all services
curl http://localhost:8000/health

# Check specific components
curl http://localhost:8000/comfyui/status
curl http://localhost:8000/rag/stats
```

## 🧪 Testing

### Smoke Tests
```bash
# Install test dependencies
pip install aiohttp

# Run comprehensive test suite
python smoke_tests.py
```

### Manual Testing
1. **Text Chat**: Send a message and verify response
2. **Voice**: Click microphone, speak, verify transcription
3. **Vision**: Upload an image, ask about it
4. **RAG**: Upload a document, ask questions about it
5. **Image Generation**: Enter prompt, generate image

## 📂 Project Structure

```
open-chat/
├── backend/                 # FastAPI backend services
│   ├── services/           # Microservice modules
│   │   ├── ollama_service.py
│   │   ├── stt_service.py
│   │   ├── tts_service.py
│   │   ├── rag_service.py
│   │   ├── vision_service.py
│   │   ├── comfyui_service.py
│   │   └── conversation_service.py
│   ├── models/             # Data schemas
│   ├── main.py            # FastAPI application
│   └── config.py          # Configuration management
├── frontend/               # Web interface
│   ├── index.html         # Main UI
│   └── chat.js           # Frontend logic
├── smoke_tests.py         # Automated testing
├── requirements.txt       # Python dependencies
├── start.sh              # Application launcher
├── .env.example          # Configuration template
└── README.md             # This documentation
```

## 🔧 API Reference

### Core Endpoints
- `GET /` - Serve web interface
- `GET /health` - Service health check
- `POST /chat` - Send chat message
- `POST /transcribe` - Audio to text conversion
- `POST /speak` - Text to audio synthesis

### Vision & Multimodal
- `GET /models` - List available models with vision capabilities
- `POST /chat` - Send message with optional image attachment

### RAG & Documents
- `GET /rag/stats` - RAG system status and statistics
- `POST /rag/upload` - Upload documents for knowledge base
- `DELETE /rag/clear` - Clear document embeddings

### Image Generation
- `GET /comfyui/status` - ComfyUI connection status
- `GET /comfyui/models` - Available generation models
- `POST /comfyui/generate` - Generate images from prompts

### Conversation Management
- `GET /conversations` - Retrieve chat history
- `GET /conversations/stats` - Conversation statistics
- `DELETE /conversations/clear` - Clear conversation history

## 🎯 Version History

### v1.3.0 (November 2025) - Image Generation Integration
- ✅ ComfyUI integration for AI image generation
- ✅ Professional gradient UI with parameter controls
- ✅ Real-time progress tracking and status monitoring
- ✅ Cross-network GPU server support

### v1.2.0 - Vision Integration
- ✅ bakllava and llava vision model support
- ✅ Image upload with drag-drop functionality
- ✅ Multi-format image processing
- ✅ Automatic vision model detection

### v1.1.0 - Enhanced Audio & RAG
- ✅ Advanced audio controls (play/pause/stop/restart)
- ✅ Document RAG with drag-drop upload
- ✅ sentence-transformers vector embeddings
- ✅ CUDA acceleration support

### v1.0.0 - Initial Release
- ✅ Core text chat functionality
- ✅ Whisper STT and ElevenLabs TTS
- ✅ Responsive web interface
- ✅ Conversation history management

## 🔍 Development Journey

This project evolved through several major phases:

1. **Foundation**: Basic chat interface with Ollama integration
2. **Audio Enhancement**: Added voice recognition and synthesis
3. **RAG Integration**: Document upload and vector search
4. **Vision Capabilities**: Multi-modal AI with image analysis
5. **Image Generation**: ComfyUI integration for AI art creation

Each iteration built upon previous work with comprehensive version tagging and professional documentation.

## 🐛 Troubleshooting

### Common Issues

**ComfyUI Connection Failed**
- Verify ComfyUI server is running on specified host:port
- Check network connectivity and firewall settings
- Ensure RealVisXL model is properly installed

**Vision Models Not Available**
- Install vision models: `ollama pull bakllava llava`
- Verify models are loaded: `ollama list`
- Check Ollama service status

**RAG Upload Errors**
- Ensure document formats are supported (.txt, .md, .pdf, .docx)
- Check file size limits and disk space
- Verify sentence-transformers installation

**Audio Issues**
- Check microphone permissions in browser
- Verify ElevenLabs API key if using cloud TTS
- Test with local pyttsx3 as fallback

### Performance Optimization
- Use CUDA-enabled GPU for embeddings and generation
- Adjust Whisper model size based on accuracy needs
- Configure appropriate batch sizes for document processing

## 🤝 Contributing

This project welcomes contributions! Areas for enhancement:
- Additional vision model support
- More document formats for RAG
- Enhanced UI components
- Docker containerization
- Performance optimizations

## 📄 License

MIT License - see LICENSE file for details.

Built with ❤️ using modern AI technologies and professional development practices.

---

**Ready to experience the future of AI interaction? Get started in minutes!** 🚀