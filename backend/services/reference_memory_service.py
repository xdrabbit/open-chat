import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReferenceMemoryService:
    """Own exact-reference document chunking, storage, retrieval, and deletion."""

    def __init__(self, document_processor, vector_store, enabled_getter):
        self.document_processor = document_processor
        self.vector_store = vector_store
        self.enabled_getter = enabled_getter

    def is_enabled(self) -> bool:
        return bool(self.enabled_getter())

    async def add_document(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        if not self.is_enabled():
            logger.warning("Reference memory service is not enabled")
            return False

        try:
            chunks = await self.document_processor.process_document(file_path, metadata)
            if not chunks:
                logger.warning(f"No chunks generated from {file_path}")
                return False

            success = await self.vector_store.add_documents(chunks)
            if success:
                logger.info(f"✅ Successfully added reference document: {file_path}")
            return success
        except Exception as e:
            logger.error(f"Failed to add reference document {file_path}: {e}")
            return False

    async def add_text_document(self, text: str, source: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        if not self.is_enabled():
            logger.warning("Reference memory service is not enabled")
            return False

        try:
            chunks = await self.document_processor.process_text(text, source, metadata)
            if not chunks:
                logger.warning(f"No chunks generated from text source {source}")
                return False

            success = await self.vector_store.add_documents(chunks)
            if success:
                logger.info(f"✅ Successfully added reference text source: {source}")
            return success
        except Exception as e:
            logger.error(f"Failed to add reference text source {source}: {e}")
            return False

    async def extract_document_text(self, file_path: str) -> str:
        try:
            return await self.document_processor.extract_text(file_path)
        except AttributeError:
            file_path_obj = Path(file_path)
            if file_path_obj.suffix.lower() in [".txt", ".md"]:
                return file_path_obj.read_text(encoding="utf-8")
            return ""
        except Exception as e:
            logger.error(f"Failed to extract document text for reference memory: {e}")
            return ""

    async def search_documents(self, query: str, context_limit: int = 3) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        try:
            return await self.vector_store.search(query, context_limit)
        except Exception as e:
            logger.error(f"Reference document search failed: {e}")
            return []

    async def delete_document(self, document_id: str) -> bool:
        if not self.is_enabled():
            return False
        return await self.vector_store.delete_document(document_id)

    async def delete_documents_by_content_hash(self, content_hash: str) -> int:
        return await self.vector_store.delete_documents_by_content_hash(content_hash)

    async def list_documents(self) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        try:
            stats = self.vector_store.get_stats()
            return [{
                "total_documents": stats.get("unique_documents", 0),
                "total_chunks": stats.get("total_chunks", 0),
                "embedding_coverage": stats.get("embedding_coverage", 0),
            }]
        except Exception as e:
            logger.error(f"Failed to list reference documents: {e}")
            return []
