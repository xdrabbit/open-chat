#!/usr/bin/env python3
"""
Test RAG System - AI Capabilities Knowledge

This script tests that the AI now understands it can generate images
thanks to the RAG system with our capabilities knowledge.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

from services.rag_service import create_rag_service

async def test_rag_capabilities_search():
    """Test that RAG can find capabilities knowledge"""
    print("🧠 Testing RAG System - AI Capabilities Knowledge")
    print("=" * 60)
    
    # Create RAG service
    rag_service = create_rag_service()
    
    if not rag_service.is_enabled():
        print("❌ RAG service not enabled - check dependencies")
        return False
    
    # Test queries that should find our capabilities knowledge
    test_queries = [
        "can you generate images",
        "show me a picture", 
        "I want to see a visualization",
        "create an image for me",
        "AI image generation capabilities",
        "visual content creation"
    ]
    
    success_count = 0
    
    for query in test_queries:
        print(f"🔍 Query: '{query}'")
        
        # Search for relevant content
        results = await rag_service.search_documents(query, context_limit=2)
        
        if results:
            print(f"  ✅ Found {len(results)} relevant knowledge chunks")
            # Show a sample of what was found
            for i, result in enumerate(results[:1]):  # Show first result
                sample = result[:100] + "..." if len(result) > 100 else result
                print(f"    📄 Sample: {sample}")
            success_count += 1
        else:
            print(f"  ❌ No relevant knowledge found")
        
        print()
    
    print("=" * 60)
    print(f"📊 Results: {success_count}/{len(test_queries)} queries found relevant knowledge")
    
    if success_count >= len(test_queries) * 0.7:  # 70% success rate
        print("🎉 RAG system successfully contains AI capabilities knowledge!")
        return True
    else:
        print("⚠️  RAG system may need more capabilities knowledge")
        return False

async def test_rag_enhancement():
    """Test the RAG enhancement function"""
    print("🔧 Testing RAG Enhancement Function:")
    print()
    
    from services.rag_service import enhance_chat_with_rag
    
    rag_service = create_rag_service()
    
    test_messages = [
        "Can you show me a sunset?",
        "I need help with image generation", 
        "What can you do with pictures?"
    ]
    
    for message in test_messages:
        print(f"Original: {message}")
        enhanced = await enhance_chat_with_rag(message, rag_service)
        print(f"Enhanced: {enhanced[:150]}...")
        print()

if __name__ == "__main__":
    async def main():
        success = await test_rag_capabilities_search()
        await test_rag_enhancement()
        
        if success:
            print("💡 The AI should now understand it can generate images!")
            print("🚀 Ready to test with actual chat requests!")
        else:
            print("🔄 May need to add more capabilities knowledge to RAG")
    
    asyncio.run(main())