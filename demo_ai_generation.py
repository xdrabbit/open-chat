#!/usr/bin/env python3
"""
Quick Demo: AI-Initiated Image Generation with Creativity Controls
Shows the key features working together
"""

import asyncio
import json
import aiohttp

async def demo_ai_generation():
    """Demonstrate the AI-initiated image generation feature"""
    print("🎭 AI-Initiated Image Generation Demo")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # Test different creativity levels with visual requests
    test_cases = [
        {
            "message": "Show me what a peaceful zen garden looks like",
            "temperature": 0.5,
            "top_p": 0.8,
            "label": "Conservative AI"
        },
        {
            "message": "Visualize a futuristic floating city in the clouds",
            "temperature": 1.0,
            "top_p": 0.9,
            "label": "Balanced AI"
        },
        {
            "message": "Create an artistic interpretation of music becoming visible",
            "temperature": 1.5,
            "top_p": 0.95,
            "label": "Creative AI"
        }
    ]
    
    async with aiohttp.ClientSession() as session:
        for i, test in enumerate(test_cases, 1):
            print(f"\n🎯 Test {i}: {test['label']}")
            print(f"🎚️  Temperature: {test['temperature']}, Top-p: {test['top_p']}")
            print(f"💬 Request: '{test['message']}'")
            
            payload = {
                "message": test["message"],
                "model": "llama3.2:latest",
                "temperature": test["temperature"],
                "top_p": test["top_p"]
            }
            
            try:
                async with session.post(f"{base_url}/chat", json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        print(f"✅ AI Response: {data['response'][:80]}...")
                        
                        if 'generated_image' in data and data['generated_image']:
                            img = data['generated_image']
                            print(f"🎨 AI Generated Image!")
                            print(f"   📍 URL: {img['url']}")
                            print(f"   💭 Reason: {img['reason']}")
                            print(f"   🎯 Style: {img['style']}")
                            print(f"   🚀 AI-Initiated: {img['ai_initiated']}")
                        else:
                            print("📝 Text-only response (no image generated)")
                    else:
                        print(f"❌ Error: {response.status}")
                        
            except Exception as e:
                print(f"❌ Connection error: {e}")
                break
                
            print("-" * 30)
            await asyncio.sleep(2)
    
    print("\n🎉 Demo Complete!")
    print("💡 Try the interactive interface at http://localhost:8000")
    print("🎭 Click 'Creativity' button to adjust AI behavior")
    print("🎨 Ask for visual content to see AI-initiated generation")

if __name__ == "__main__":
    asyncio.run(demo_ai_generation())