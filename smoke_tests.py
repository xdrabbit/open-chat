#!/usr/bin/env python3
"""
Open Chat Smoke Tests
Comprehensive automated testing for all major features
"""

import asyncio
import aiohttp
import json
import time
import sys
import os
from pathlib import Path

# Configuration
BASE_URL = "http://localhost:8000"
COMFYUI_HOST = "192.168.0.45:8188"
TEST_TIMEOUT = 30

class SmokeTestSuite:
    def __init__(self):
        self.session = None
        self.test_results = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def log_result(self, test_name, passed, message="", duration=0):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name} ({duration:.2f}s)")
        if message:
            print(f"    {message}")
        
        self.test_results.append({
            "test": test_name,
            "passed": passed,
            "message": message,
            "duration": duration
        })

    async def test_health_check(self):
        """Test basic health endpoint"""
        start_time = time.time()
        try:
            async with self.session.get(f"{BASE_URL}/health") as response:
                data = await response.json()
                
                # Check response structure
                required_keys = ["status", "ollama", "tts", "stt"]
                missing_keys = [key for key in required_keys if key not in data]
                
                if missing_keys:
                    self.log_result("Health Check", False, 
                                  f"Missing keys: {missing_keys}", 
                                  time.time() - start_time)
                    return
                
                # Check service status
                if data["status"] != "healthy":
                    self.log_result("Health Check", False, 
                                  f"Status not healthy: {data['status']}", 
                                  time.time() - start_time)
                    return
                
                self.log_result("Health Check", True, 
                              f"All services: {data}", 
                              time.time() - start_time)
                
        except Exception as e:
            self.log_result("Health Check", False, str(e), time.time() - start_time)

    async def test_models_endpoint(self):
        """Test models listing and vision detection"""
        start_time = time.time()
        try:
            async with self.session.get(f"{BASE_URL}/models") as response:
                data = await response.json()
                
                if "models" not in data:
                    self.log_result("Models Endpoint", False, 
                                  "No models key in response", 
                                  time.time() - start_time)
                    return
                
                # Check for vision models
                vision_models = [m for m in data["models"] if m.get("supports_vision")]
                
                self.log_result("Models Endpoint", True, 
                              f"Found {len(data['models'])} models, {len(vision_models)} with vision", 
                              time.time() - start_time)
                
        except Exception as e:
            self.log_result("Models Endpoint", False, str(e), time.time() - start_time)

    async def test_conversation_stats(self):
        """Test conversation statistics"""
        start_time = time.time()
        try:
            async with self.session.get(f"{BASE_URL}/conversations/stats") as response:
                data = await response.json()
                
                required_keys = ["total_messages", "total_conversations"]
                missing_keys = [key for key in required_keys if key not in data]
                
                if missing_keys:
                    self.log_result("Conversation Stats", False, 
                                  f"Missing keys: {missing_keys}", 
                                  time.time() - start_time)
                    return
                
                self.log_result("Conversation Stats", True, 
                              f"Stats: {data}", 
                              time.time() - start_time)
                
        except Exception as e:
            self.log_result("Conversation Stats", False, str(e), time.time() - start_time)

    async def test_voices_endpoint(self):
        """Test TTS voices endpoint"""
        start_time = time.time()
        try:
            async with self.session.get(f"{BASE_URL}/voices") as response:
                data = await response.json()
                
                if "voices" not in data:
                    self.log_result("Voices Endpoint", False, 
                                  "No voices key in response", 
                                  time.time() - start_time)
                    return
                
                self.log_result("Voices Endpoint", True, 
                              f"Found {len(data['voices'])} voices", 
                              time.time() - start_time)
                
        except Exception as e:
            self.log_result("Voices Endpoint", False, str(e), time.time() - start_time)

    async def test_rag_status(self):
        """Test RAG system status"""
        start_time = time.time()
        try:
            async with self.session.get(f"{BASE_URL}/rag/stats") as response:
                data = await response.json()
                
                required_keys = ["enabled", "documents_count", "embedding_model"]
                missing_keys = [key for key in required_keys if key not in data]
                
                if missing_keys:
                    self.log_result("RAG Status", False, 
                                  f"Missing keys: {missing_keys}", 
                                  time.time() - start_time)
                    return
                
                self.log_result("RAG Status", True, 
                              f"RAG enabled: {data['enabled']}, docs: {data['documents_count']}", 
                              time.time() - start_time)
                
        except Exception as e:
            self.log_result("RAG Status", False, str(e), time.time() - start_time)

    async def test_comfyui_status(self):
        """Test ComfyUI connection and status"""
        start_time = time.time()
        try:
            async with self.session.get(f"{BASE_URL}/comfyui/status") as response:
                data = await response.json()
                
                if "connected" not in data:
                    self.log_result("ComfyUI Status", False, 
                                  "No connected key in response", 
                                  time.time() - start_time)
                    return
                
                if data["connected"]:
                    system_info = data.get("system_info", {})
                    version = system_info.get("comfyui_version", "Unknown")
                    self.log_result("ComfyUI Status", True, 
                                  f"Connected to ComfyUI v{version}", 
                                  time.time() - start_time)
                else:
                    self.log_result("ComfyUI Status", False, 
                                  "ComfyUI not connected", 
                                  time.time() - start_time)
                
        except Exception as e:
            self.log_result("ComfyUI Status", False, str(e), time.time() - start_time)

    async def test_chat_basic(self):
        """Test basic chat functionality"""
        start_time = time.time()
        try:
            test_message = "Hello, this is a smoke test. Please respond briefly."
            
            form_data = aiohttp.FormData()
            form_data.add_field('message', test_message)
            form_data.add_field('model', 'llama3.2:latest')
            
            async with self.session.post(f"{BASE_URL}/chat", data=form_data) as response:
                if response.status != 200:
                    self.log_result("Basic Chat", False, 
                                  f"HTTP {response.status}", 
                                  time.time() - start_time)
                    return
                
                data = await response.json()
                
                if "response" not in data:
                    self.log_result("Basic Chat", False, 
                                  "No response key in chat response", 
                                  time.time() - start_time)
                    return
                
                response_text = data["response"]
                if len(response_text) < 5:
                    self.log_result("Basic Chat", False, 
                                  f"Response too short: '{response_text}'", 
                                  time.time() - start_time)
                    return
                
                self.log_result("Basic Chat", True, 
                              f"Got response: '{response_text[:50]}...'", 
                              time.time() - start_time)
                
        except Exception as e:
            self.log_result("Basic Chat", False, str(e), time.time() - start_time)

    async def test_image_generation(self):
        """Test ComfyUI image generation (if available)"""
        start_time = time.time()
        try:
            # First check if ComfyUI is available
            async with self.session.get(f"{BASE_URL}/comfyui/status") as response:
                status_data = await response.json()
                
                if not status_data.get("connected"):
                    self.log_result("Image Generation", False, 
                                  "ComfyUI not connected - skipping generation test", 
                                  time.time() - start_time)
                    return
            
            # Test image generation
            form_data = aiohttp.FormData()
            form_data.add_field('prompt', 'a simple red circle on white background')
            form_data.add_field('negative_prompt', 'blurry, complex')
            form_data.add_field('width', '512')
            form_data.add_field('height', '512')
            form_data.add_field('steps', '15')
            form_data.add_field('cfg', '7')
            
            # Use longer timeout for image generation
            timeout = aiohttp.ClientTimeout(total=120)
            async with self.session.post(f"{BASE_URL}/comfyui/generate", 
                                       data=form_data, 
                                       timeout=timeout) as response:
                if response.status != 200:
                    self.log_result("Image Generation", False, 
                                  f"HTTP {response.status}", 
                                  time.time() - start_time)
                    return
                
                data = await response.json()
                
                if not data.get("success"):
                    self.log_result("Image Generation", False, 
                                  f"Generation failed: {data}", 
                                  time.time() - start_time)
                    return
                
                image_filename = data.get("image_filename")
                if not image_filename:
                    self.log_result("Image Generation", False, 
                                  "No image filename returned", 
                                  time.time() - start_time)
                    return
                
                self.log_result("Image Generation", True, 
                              f"Generated image: {image_filename}", 
                              time.time() - start_time)
                
        except asyncio.TimeoutError:
            self.log_result("Image Generation", False, 
                          "Timeout waiting for image generation", 
                          time.time() - start_time)
        except Exception as e:
            self.log_result("Image Generation", False, str(e), time.time() - start_time)

    async def run_all_tests(self):
        """Run all smoke tests"""
        print("🧪 Open Chat Smoke Test Suite")
        print("=" * 50)
        
        # Basic API tests
        await self.test_health_check()
        await self.test_models_endpoint()
        await self.test_conversation_stats()
        await self.test_voices_endpoint()
        await self.test_rag_status()
        await self.test_comfyui_status()
        
        # Functional tests
        await self.test_chat_basic()
        await self.test_image_generation()
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 Test Summary")
        print("=" * 50)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["passed"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n🔍 Failed Tests:")
            for result in self.test_results:
                if not result["passed"]:
                    print(f"  ❌ {result['test']}: {result['message']}")
        
        return failed_tests == 0

async def main():
    """Main test runner"""
    print("Starting Open Chat smoke tests...")
    print(f"Target URL: {BASE_URL}")
    print(f"ComfyUI Host: {COMFYUI_HOST}")
    print()
    
    try:
        async with SmokeTestSuite() as suite:
            success = await suite.run_all_tests()
            
            if success:
                print("\n🎉 All smoke tests passed!")
                sys.exit(0)
            else:
                print("\n💥 Some tests failed!")
                sys.exit(1)
                
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test suite error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())