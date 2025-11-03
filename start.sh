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

# Check if Ollama is running
echo "🔍 Checking Ollama connection..."
if ! curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "⚠️  Ollama is not running on localhost:11434"
    echo "   Please start Ollama first: ollama serve"
    echo "   Then download a model: ollama pull llama3.2"
    read -p "Press Enter to continue anyway..."
fi

# Start the application
echo "🎯 Starting Open Chat backend..."
cd backend
python main.py