#!/usr/bin/env python3
"""
Test AI Capabilities Knowledge Integration

This script tests if the RAG system is successfully providing the AI with 
knowledge about its image generation capabilities.
"""

import asyncio
import httpx
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_ai_capabilities_knowledge():
    """Test if AI now understands its image generation capabilities"""
    
    base_url = "http://localhost:8000"
    
    # Test queries that should now work correctly
    test_queries = [
        "Can you generate images?",
        "Show me a beautiful sunset",
        "I need you to create a picture",
        "Can you draw something for me?",
        "Are you able to make visual content?"
    ]
    
    logger.info("🧪 Testing AI Capabilities Knowledge Integration")
    logger.info("=" * 60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, query in enumerate(test_queries, 1):
            logger.info(f"🔍 Test {i}/5: '{query}'")
            
            try:
                # Send chat request
                response = await client.post(
                    f"{base_url}/api/chat",
                    json={
                        "message": query,
                        "model": "smollm2:latest",
                        "temperature": 0.7,
                        "top_p": 0.9
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    ai_response = data.get("response", "")
                    
                    # Check if response indicates understanding of capabilities
                    positive_indicators = [
                        "generate", "create", "image", "visual", "picture", 
                        "illustration", "show", "draw", "paint", "artwork"
                    ]
                    
                    negative_indicators = [
                        "can't", "cannot", "unable", "don't have the ability",
                        "text-based model", "not capable", "sorry"
                    ]
                    
                    has_positive = any(indicator in ai_response.lower() for indicator in positive_indicators)
                    has_negative = any(indicator in ai_response.lower() for indicator in negative_indicators)
                    
                    if has_positive and not has_negative:
                        logger.info(f"✅ GOOD: AI shows understanding of capabilities")
                    elif has_negative:
                        logger.warning(f"⚠️  CONCERN: AI still claims inability")
                    else:
                        logger.info(f"ℹ️  NEUTRAL: Response unclear about capabilities")
                    
                    # Show first 150 chars of response
                    preview = ai_response[:150] + "..." if len(ai_response) > 150 else ai_response
                    logger.info(f"📝 Response: {preview}")
                    
                    # Check if image was generated
                    if data.get("generated_image"):
                        logger.info(f"🎨 ✅ IMAGE GENERATED: {data['generated_image']['filename']}")
                    else:
                        logger.info(f"🎨 ❌ No image generated")
                        
                else:
                    logger.error(f"❌ HTTP Error: {response.status_code}")
                
            except Exception as e:
                logger.error(f"❌ Request failed: {e}")
            
            logger.info("-" * 60)
            await asyncio.sleep(1)  # Brief pause between tests

async def check_rag_status():
    """Check if RAG system is working"""
    base_url = "http://localhost:8000"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base_url}/health")
            
            if response.status_code == 200:
                health_data = response.json()
                rag_status = health_data.get("rag_service", {})
                
                if rag_status.get("enabled"):
                    logger.info("✅ RAG service is enabled and running")
                    logger.info(f"📚 Document count: {rag_status.get('document_count', 'unknown')}")
                else:
                    logger.warning("⚠️  RAG service is not enabled")
                    
                return rag_status.get("enabled", False)
            else:
                logger.error(f"❌ Health check failed: {response.status_code}")
                return False
                
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        return False

if __name__ == "__main__":
    async def main():
        logger.info("🔬 Testing AI Capabilities Knowledge Integration")
        logger.info("🎯 Goal: Verify AI understands it can generate images")
        logger.info("=" * 60)
        
        # Check RAG status first
        rag_working = await check_rag_status()
        
        if rag_working:
            logger.info("✅ RAG system is operational, proceeding with tests...")
            await test_ai_capabilities_knowledge()
        else:
            logger.error("❌ RAG system not working, tests may not be meaningful")
            
        logger.info("=" * 60)
        logger.info("🎉 Test complete!")
        logger.info("💡 If AI still claims inability, the knowledge may need time to propagate")
    
    asyncio.run(main())