#!/usr/bin/env python3
"""
Test script for AI-initiated image generation feature
Demonstrates the enhanced creativity controls and AI function calling
"""

import asyncio
import json
import aiohttp
import sys
from datetime import datetime

class AIGenerationTester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        
    async def test_creativity_chat(self, message, temperature=0.7, top_p=0.9):
        """Test chat with creativity controls"""
        print(f"\n🧠 Testing creativity chat with temperature={temperature}, top_p={top_p}")
        print(f"📝 Message: '{message}'")
        
        payload = {
            "message": message,
            "model": "llama3.2:latest",
            "temperature": temperature,
            "top_p": top_p
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{self.base_url}/chat", json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        print(f"✅ Chat Response: {data['response'][:100]}...")
                        
                        # Check for AI-generated image
                        if 'generated_image' in data and data['generated_image']:
                            img_data = data['generated_image']
                            print(f"🎨 AI Generated Image!")
                            print(f"   📍 URL: {img_data['url']}")
                            print(f"   💭 Reason: {img_data['reason']}")
                            print(f"   🎯 Prompt: {img_data['prompt'][:60]}...")
                            print(f"   🎭 Style: {img_data['style']}")
                            print(f"   🤖 AI Initiated: {img_data['ai_initiated']}")
                            return True
                        else:
                            print("📝 Text-only response (no image generated)")
                            return False
                    else:
                        print(f"❌ Error: {response.status} - {await response.text()}")
                        return False
            except Exception as e:
                print(f"❌ Connection error: {e}")
                return False

    async def test_visual_requests(self):
        """Test various requests that should trigger AI image generation"""
        visual_prompts = [
            "Show me what a futuristic city would look like",
            "Can you illustrate the concept of machine learning?",
            "Draw a peaceful mountain landscape",
            "Visualize how photosynthesis works",
            "Create an image of a cozy reading nook"
        ]
        
        print("\n🎨 Testing AI-initiated image generation with visual requests...")
        
        results = []
        for i, prompt in enumerate(visual_prompts, 1):
            print(f"\n--- Test {i}/{len(visual_prompts)} ---")
            result = await self.test_creativity_chat(prompt, temperature=0.8, top_p=0.9)
            results.append(result)
            await asyncio.sleep(2)  # Brief pause between requests
            
        success_rate = sum(results) / len(results) * 100
        print(f"\n🎯 Image Generation Success Rate: {success_rate:.1f}% ({sum(results)}/{len(results)})")
        return success_rate > 50  # Consider successful if > 50% generate images

    async def test_creativity_levels(self):
        """Test different creativity levels"""
        prompt = "Describe and show me an alien planet"
        
        creativity_levels = [
            (0.3, 0.5, "Conservative"),
            (0.7, 0.9, "Balanced"), 
            (1.2, 0.95, "Creative"),
            (1.8, 1.0, "Highly Creative")
        ]
        
        print("\n🎭 Testing different creativity levels...")
        
        for temp, top_p, label in creativity_levels:
            print(f"\n--- {label} Mode (temp={temp}, top_p={top_p}) ---")
            await self.test_creativity_chat(prompt, temperature=temp, top_p=top_p)
            await asyncio.sleep(2)
            
        return True

    async def test_function_calling_detection(self):
        """Test the AI's function calling detection"""
        print("\n🔧 Testing function calling detection...")
        
        # Direct requests that should definitely trigger image generation
        direct_requests = [
            "Please create an image of a sunset over the ocean",
            "Generate a picture of a robot in a garden",
            "I need a visual representation of data flowing through networks"
        ]
        
        for request in direct_requests:
            print(f"\n🎯 Direct visual request: '{request}'")
            result = await self.test_creativity_chat(request, temperature=0.9, top_p=0.9)
            if not result:
                print("⚠️  Expected image generation but got text-only response")
            await asyncio.sleep(2)
        
        return True

    async def run_comprehensive_test(self):
        """Run all tests"""
        print("🚀 Starting AI-Initiated Image Generation Test Suite")
        print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # Test 1: Basic health check
        print("\n1️⃣ Testing server health...")
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        health_data = await response.json()
                        print(f"✅ Server healthy: {health_data}")
                    else:
                        print(f"❌ Health check failed: {response.status}")
                        return False
            except Exception as e:
                print(f"❌ Cannot connect to server: {e}")
                return False
        
        # Test 2: Visual requests
        print("\n2️⃣ Testing visual content requests...")
        visual_success = await self.test_visual_requests()
        
        # Test 3: Creativity levels
        print("\n3️⃣ Testing creativity parameter effects...")
        await self.test_creativity_levels()
        
        # Test 4: Function calling
        print("\n4️⃣ Testing function calling detection...")
        await self.test_function_calling_detection()
        
        print("\n" + "=" * 60)
        print("🎉 Test Suite Complete!")
        print(f"⏰ Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if visual_success:
            print("✅ AI-initiated image generation is working!")
            print("💡 Try opening http://localhost:8000 to test the interactive interface")
            print("🎭 Use the 'Creativity' button to adjust AI behavior")
        else:
            print("⚠️  AI-initiated image generation needs attention")
            print("🔧 Check Ollama models and ComfyUI connection")
        
        return visual_success

async def main():
    """Main test runner"""
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        # Quick test mode
        tester = AIGenerationTester()
        print("🏃‍♂️ Running quick test...")
        await tester.test_creativity_chat("Show me a beautiful garden with flowers", temperature=0.8, top_p=0.9)
    else:
        # Full test suite
        tester = AIGenerationTester()
        await tester.run_comprehensive_test()

if __name__ == "__main__":
    asyncio.run(main())