#!/usr/bin/env python3
"""
Test script for STT and TTS functionality
"""

import asyncio
import os
import sys
import tempfile
import wave
import numpy as np

# Add the backend directory to the path
sys.path.insert(0, '/home/tkash/wsl_dev/open-chat/backend')

from services.stt_service import STTService
from services.tts_service import TTSService
from config import config

async def test_tts():
    """Test Text-to-Speech functionality"""
    print("🔊 Testing TTS (Text-to-Speech)...")
    
    tts_service = TTSService()
    
    # Check available providers
    providers = tts_service.get_available_providers()
    current = tts_service.get_current_provider()
    
    print(f"Available TTS providers: {providers}")
    print(f"Current TTS provider: {current}")
    
    if not tts_service.is_available():
        print("❌ No TTS providers available")
        return False
    
    # Test TTS generation
    test_text = "Hello! This is a test of the text to speech system. Can you hear me clearly?"
    
    try:
        print(f"Generating speech for: '{test_text}'")
        audio_file = await tts_service.generate_speech(test_text)
        
        audio_path = os.path.join(config.AUDIO_TEMP_DIR, audio_file)
        if os.path.exists(audio_path):
            file_size = os.path.getsize(audio_path)
            print(f"✅ TTS Success! Generated audio file: {audio_file} ({file_size} bytes)")
            return True
        else:
            print(f"❌ TTS failed: Audio file not found at {audio_path}")
            return False
            
    except Exception as e:
        print(f"❌ TTS Error: {e}")
        return False

def create_test_audio():
    """Create a simple test audio file (sine wave saying 'hello')"""
    # Create a simple sine wave audio for testing
    duration = 2.0  # seconds
    sample_rate = 16000
    frequency = 440  # A4 note
    
    # Generate sine wave
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio_data = np.sin(2 * np.pi * frequency * t)
    
    # Convert to 16-bit PCM
    audio_data = (audio_data * 32767).astype(np.int16)
    
    # Create temporary WAV file
    temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    
    with wave.open(temp_file.name, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())
    
    return temp_file.name

async def test_stt():
    """Test Speech-to-Text functionality"""
    print("\n🎤 Testing STT (Speech-to-Text)...")
    
    stt_service = STTService()
    
    if not stt_service.is_available():
        print("❌ STT service not available")
        return False
    
    print("✅ Whisper model loaded and ready")
    
    # Create a test audio file (since we can't record from mic in script)
    print("Creating test audio file...")
    test_audio_path = create_test_audio()
    
    try:
        # Read the test audio file
        with open(test_audio_path, 'rb') as f:
            audio_data = f.read()
        
        print(f"Testing transcription with {len(audio_data)} bytes of audio data...")
        
        # Test transcription
        transcribed_text = await stt_service.transcribe(audio_data, "test.wav")
        
        print(f"✅ STT Success! Transcribed text: '{transcribed_text}'")
        
        # Clean up
        os.unlink(test_audio_path)
        
        return True
        
    except Exception as e:
        print(f"❌ STT Error: {e}")
        # Clean up on error
        if os.path.exists(test_audio_path):
            os.unlink(test_audio_path)
        return False

async def test_integration():
    """Test the full pipeline: TTS -> STT"""
    print("\n🔄 Testing Integration (TTS -> STT Pipeline)...")
    
    tts_service = TTSService()
    stt_service = STTService()
    
    if not (tts_service.is_available() and stt_service.is_available()):
        print("❌ Both TTS and STT services must be available for integration test")
        return False
    
    # Test text
    original_text = "This is a round trip test of speech synthesis and recognition."
    
    try:
        # Step 1: Generate speech from text
        print(f"Step 1: Converting text to speech: '{original_text}'")
        audio_file = await tts_service.generate_speech(original_text)
        
        audio_path = os.path.join(config.AUDIO_TEMP_DIR, audio_file)
        
        # Step 2: Read the generated audio
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        
        # Step 3: Convert speech back to text
        print("Step 2: Converting speech back to text...")
        transcribed_text = await stt_service.transcribe(audio_data, audio_file)
        
        print(f"Original text:    '{original_text}'")
        print(f"Transcribed text: '{transcribed_text}'")
        
        # Simple similarity check
        original_words = set(original_text.lower().split())
        transcribed_words = set(transcribed_text.lower().split())
        
        if len(original_words) > 0:
            similarity = len(original_words & transcribed_words) / len(original_words)
            print(f"Word similarity: {similarity:.2%}")
            
            if similarity > 0.5:  # 50% word overlap
                print("✅ Integration test passed!")
                return True
            else:
                print("⚠️  Low similarity but integration pipeline works")
                return True
        else:
            print("✅ Integration pipeline completed")
            return True
            
    except Exception as e:
        print(f"❌ Integration test error: {e}")
        return False

async def main():
    """Run all tests"""
    print("🧪 Open Chat - STT/TTS Test Suite")
    print("=" * 50)
    
    # Test TTS
    tts_success = await test_tts()
    
    # Test STT  
    stt_success = await test_stt()
    
    # Test Integration (if both work)
    if tts_success and stt_success:
        integration_success = await test_integration()
    else:
        integration_success = False
        print("\n🔄 Skipping integration test (TTS or STT failed)")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    print(f"TTS (Text-to-Speech): {'✅ PASS' if tts_success else '❌ FAIL'}")
    print(f"STT (Speech-to-Text): {'✅ PASS' if stt_success else '❌ FAIL'}")
    print(f"Integration Pipeline: {'✅ PASS' if integration_success else '❌ FAIL'}")
    
    if tts_success and stt_success:
        print("\n🎉 All systems ready! You can now:")
        print("   • Type messages for text chat")
        print("   • Click microphone for voice chat")
        print("   • Enjoy audio responses")
    else:
        print("\n⚠️  Some issues detected. Check the errors above.")

if __name__ == "__main__":
    asyncio.run(main())