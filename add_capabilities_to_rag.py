#!/usr/bin/env python3
"""
Add AI Capabilities Knowledge to RAG System

This script adds the AI_CAPABILITIES_KNOWLEDGE.md document to the RAG system
so the AI will understand its image generation capabilities.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

from services.rag_service import create_rag_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def add_capabilities_knowledge():
    """Add AI capabilities knowledge to RAG system"""
    try:
        # Create RAG service
        rag_service = create_rag_service()
        
        # Initialize if needed
        await rag_service.initialize()
        
        if not rag_service.is_enabled():
            logger.error("❌ RAG service is not enabled. Check dependencies.")
            return False
        
        # Path to our capabilities document
        capabilities_doc = Path("AI_CAPABILITIES_KNOWLEDGE.md")
        
        if not capabilities_doc.exists():
            logger.error(f"❌ Capabilities document not found: {capabilities_doc}")
            return False
        
        # Add the document with metadata
        metadata = {
            "title": "AI Image Generation Capabilities",
            "type": "system_knowledge", 
            "priority": "high",
            "description": "Core knowledge about AI image generation capabilities",
            "tags": ["capabilities", "image_generation", "system", "functions"]
        }
        
        logger.info(f"📄 Adding capabilities document to RAG system...")
        success = await rag_service.add_document(str(capabilities_doc), metadata)
        
        if success:
            logger.info("✅ Successfully added AI capabilities knowledge to RAG system!")
            logger.info("🧠 The AI will now understand its image generation capabilities")
        else:
            logger.error("❌ Failed to add capabilities document to RAG system")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ Error adding capabilities knowledge: {e}")
        return False

async def test_rag_search():
    """Test RAG search for image generation capabilities"""
    try:
        rag_service = create_rag_service()
        
        if not rag_service.is_enabled():
            logger.warning("⚠️  RAG service not enabled for testing")
            return
        
        # Test search queries
        test_queries = [
            "can you generate images",
            "image generation capabilities", 
            "show me a picture",
            "AI image functions"
        ]
        
        logger.info("🔍 Testing RAG search for capabilities knowledge...")
        
        for query in test_queries:
            results = await rag_service.search_documents(query, context_limit=2)
            if results:
                logger.info(f"✅ Query '{query}' found {len(results)} relevant chunks")
            else:
                logger.warning(f"⚠️  Query '{query}' found no relevant chunks")
                
    except Exception as e:
        logger.error(f"❌ Error testing RAG search: {e}")

if __name__ == "__main__":
    async def main():
        logger.info("🎨 Adding AI Capabilities Knowledge to RAG System")
        logger.info("=" * 60)
        
        # Add capabilities knowledge
        success = await add_capabilities_knowledge()
        
        if success:
            # Test the search
            await test_rag_search()
            
            logger.info("=" * 60)
            logger.info("🎉 Setup complete! The AI now knows it can generate images.")
            logger.info("💡 Next time a user asks for images, the AI should respond correctly.")
        else:
            logger.error("💥 Setup failed. Check logs above for details.")
    
    asyncio.run(main())