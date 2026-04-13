#!/bin/bash

# Open Chat Startup Script
echo "🚀 Starting Open Chat..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "📋 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
mkdir -p temp_audio

# Copy example environment file if .env doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file from example..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your settings before running!"
    read -p "Press Enter to continue after editing .env file..."
fi

MODEL_PROVIDER=$(grep -E '^[[:space:]]*MODEL_PROVIDER=' .env | tail -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
OPENAI_API_KEY=$(grep -E '^[[:space:]]*OPENAI_API_KEY=' .env | tail -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)

if [ -z "$MODEL_PROVIDER" ]; then
    MODEL_PROVIDER="openai"
fi

if [ "$MODEL_PROVIDER" = "openai" ]; then
    echo "🔍 Checking OpenAI configuration..."
    if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your_openai_api_key_here" ]; then
        echo "⚠️  OPENAI_API_KEY is missing in .env"
        echo "   Add your key before starting the backend."
        read -p "Press Enter to continue anyway..."
    fi
else
    echo "🔍 Checking Ollama connection..."
    if ! curl -s http://localhost:11434/api/tags > /dev/null; then
        echo "⚠️  Ollama is not running on localhost:11434"
        echo "   Please start Ollama first: ollama serve"
        echo "   Then download a model: ollama pull llama3.2"
        read -p "Press Enter to continue anyway..."
    fi
fi

# Start the application
echo "🎯 Starting Open Chat backend..."
cd backend
python main.py
