"""
RAG (Retrieval-Augmented Generation) Service for Open Chat

Enhanced implementation supporting document processing, vector search,
and context retrieval for improved AI responses.
"""

import os
import json
import hashlib
import logging
import sqlite3
from typing import List, Dict, Optional, Any, Union
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod

# Try to import optional dependencies
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

logger = logging.getLogger(__name__)

class DocumentProcessor(ABC):
    """Abstract base class for document processing"""
    
    @abstractmethod
    async def process_document(self, file_path: str, metadata: Dict[str, Any] = None) -> List[Dict]:
        """Process a document and return chunks with embeddings"""
        pass
    
    @abstractmethod
    def get_supported_formats(self) -> List[str]:
        """Return list of supported file formats"""
        pass

class VectorStore(ABC):
    """Abstract base class for vector storage and retrieval"""
    
    @abstractmethod
    async def add_documents(self, documents: List[Dict]) -> bool:
        """Add documents to vector store"""
        pass
    
    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search for relevant documents"""
        pass
    
    @abstractmethod
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document from the store"""
        pass

class SimpleDocumentProcessor(DocumentProcessor):
    """Enhanced document processor with multiple format support"""
    
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    async def process_document(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Process document and return chunks"""
        try:
            file_path_obj = Path(file_path)
            
            if not file_path_obj.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Extract text based on file type
            if file_path_obj.suffix.lower() == '.pdf':
                text = await self._extract_pdf_text(file_path_obj)
            elif file_path_obj.suffix.lower() in ['.txt', '.md']:
                text = await self._extract_text_file(file_path_obj)
            else:
                raise ValueError(f"Unsupported file format: {file_path_obj.suffix}")
            
            # Create chunks
            chunks = self._create_chunks(text)
            
            # Prepare document chunks
            document_chunks = []
            doc_id = hashlib.md5(f"{file_path}:{text[:100]}".encode()).hexdigest()
            
            for i, chunk in enumerate(chunks):
                document_chunks.append({
                    'id': hashlib.md5(f"{doc_id}:{i}:{chunk}".encode()).hexdigest(),
                    'document_id': doc_id,
                    'content': chunk,
                    'metadata': {
                        **(metadata or {}),
                        'source': str(file_path),
                        'chunk_index': i,
                        'total_chunks': len(chunks)
                    },
                    'created_at': datetime.now().isoformat()
                })
            
            logger.info(f"Processed {file_path}: {len(chunks)} chunks")
            return document_chunks
            
        except Exception as e:
            logger.error(f"Failed to process document {file_path}: {e}")
            return []
    
    async def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from PDF file"""
        if not PDF_SUPPORT:
            raise ImportError("PyPDF2 not available for PDF processing")
        
        try:
            text = ""
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            return text
        except Exception as e:
            logger.error(f"Failed to extract PDF text: {e}")
            raise
    
    async def _extract_text_file(self, file_path: Path) -> str:
        """Extract text from text file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            logger.error(f"Failed to read text file: {e}")
            raise
    
    def _create_chunks(self, text: str) -> List[str]:
        """Split text into overlapping chunks"""
        if not text.strip():
            return []
        
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk = " ".join(chunk_words)
            chunks.append(chunk)
            
            if i + self.chunk_size >= len(words):
                break
        
        return chunks
    
    def get_supported_formats(self) -> List[str]:
        """Return supported file formats"""
        formats = [".txt", ".md"]
        if PDF_SUPPORT:
            formats.append(".pdf")
        return formats

class SQLiteVectorStore(VectorStore):
    """SQLite-based vector store with optional embedding support"""
    
    def __init__(self, db_path: str = "rag_vectors.db", model_name: str = "all-MiniLM-L6-v2"):
        self.db_path = db_path
        self.model_name = model_name
        self.model = None
        
        if EMBEDDINGS_AVAILABLE:
            try:
                logger.info(f"Loading embedding model: {model_name}")
                self.model = SentenceTransformer(model_name)
                logger.info("✅ Embedding model loaded")
            except Exception as e:
                logger.warning(f"Failed to load embedding model: {e}")
    
    async def initialize(self):
        """Initialize the vector store database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vector_documents (
                    id TEXT PRIMARY KEY,
                    document_id TEXT,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    embedding BLOB,
                    created_at TEXT
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_id ON vector_documents(document_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_content ON vector_documents(content)")
            
            conn.commit()
            conn.close()
            
            logger.info("✅ Vector store database initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise
    
    async def add_documents(self, documents: List[Dict]) -> bool:
        """Add documents to vector store"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for doc in documents:
                # Generate embedding if model is available
                embedding = None
                if self.model:
                    try:
                        embedding_vector = self.model.encode(doc['content'])
                        embedding = embedding_vector.tobytes()
                    except Exception as e:
                        logger.warning(f"Failed to generate embedding: {e}")
                
                cursor.execute("""
                    INSERT OR REPLACE INTO vector_documents
                    (id, document_id, content, metadata, embedding, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    doc['id'],
                    doc['document_id'],
                    doc['content'],
                    json.dumps(doc['metadata']),
                    embedding,
                    doc['created_at']
                ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Added {len(documents)} document chunks to vector store")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add documents to vector store: {e}")
            return False
    
    async def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search for relevant documents"""
        try:
            if self.model:
                return await self._vector_search(query, top_k)
            else:
                return await self._keyword_search(query, top_k)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    async def _vector_search(self, query: str, top_k: int) -> List[Dict]:
        """Vector similarity search"""
        try:
            query_embedding = self.model.encode(query)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, document_id, content, metadata, embedding
                FROM vector_documents
                WHERE embedding IS NOT NULL
            """)
            
            results = []
            for row in cursor.fetchall():
                doc_id, document_id, content, metadata_str, embedding_bytes = row
                
                try:
                    doc_embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
                    
                    # Calculate cosine similarity
                    similarity = np.dot(query_embedding, doc_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding)
                    )
                    
                    results.append({
                        'id': doc_id,
                        'document_id': document_id,
                        'content': content,
                        'metadata': json.loads(metadata_str),
                        'similarity': float(similarity)
                    })
                except Exception as e:
                    logger.warning(f"Failed to process embedding for {doc_id}: {e}")
                    continue
            
            conn.close()
            
            # Sort by similarity and return top results
            results.sort(key=lambda x: x['similarity'], reverse=True)
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    async def _keyword_search(self, query: str, top_k: int) -> List[Dict]:
        """Keyword-based search fallback"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query_terms = query.lower().split()
            like_conditions = []
            params = []
            
            for term in query_terms:
                like_conditions.append("LOWER(content) LIKE ?")
                params.append(f"%{term}%")
            
            where_clause = " AND ".join(like_conditions)
            
            cursor.execute(f"""
                SELECT id, document_id, content, metadata
                FROM vector_documents
                WHERE {where_clause}
                LIMIT ?
            """, params + [top_k])
            
            results = []
            for row in cursor.fetchall():
                doc_id, document_id, content, metadata_str = row
                results.append({
                    'id': doc_id,
                    'document_id': document_id,
                    'content': content,
                    'metadata': json.loads(metadata_str),
                    'similarity': 1.0  # Placeholder
                })
            
            conn.close()
            return results
            
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete all chunks of a document"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM vector_documents WHERE document_id = ?", (document_id,))
            deleted_count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            logger.info(f"Deleted {deleted_count} chunks for document {document_id}")
            return deleted_count > 0
            
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM vector_documents")
            total_chunks = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT document_id) FROM vector_documents")
            unique_docs = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM vector_documents WHERE embedding IS NOT NULL")
            embedded_chunks = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_chunks': total_chunks,
                'unique_documents': unique_docs,
                'embedded_chunks': embedded_chunks,
                'embedding_coverage': embedded_chunks / total_chunks if total_chunks > 0 else 0,
                'model': self.model_name if self.model else None
            }
            
        except Exception as e:
            logger.error(f"Failed to get vector store stats: {e}")
            return {}

class RAGService:
    """Enhanced RAG service with full functionality"""
    
    def __init__(self, db_path: str = "rag_vectors.db", model_name: str = "all-MiniLM-L6-v2"):
        self.document_processor = SimpleDocumentProcessor()
        self.vector_store = SQLiteVectorStore(db_path, model_name)
        self.enabled = False
        
    async def initialize(self):
        """Initialize RAG components"""
        try:
            await self.vector_store.initialize()
            self.enabled = True
            logger.info("✅ RAG service initialized and enabled")
        except Exception as e:
            logger.error(f"Failed to initialize RAG service: {e}")
            self.enabled = False
    
    async def add_document(self, file_path: str, metadata: Dict[str, Any] = None) -> bool:
        """Add a document to the RAG system"""
        if not self.enabled:
            logger.warning("RAG service is not enabled")
            return False
        
        try:
            # Process document into chunks
            chunks = await self.document_processor.process_document(file_path, metadata)
            
            if not chunks:
                logger.warning(f"No chunks generated from {file_path}")
                return False
            
            # Add to vector store
            success = await self.vector_store.add_documents(chunks)
            
            if success:
                logger.info(f"✅ Successfully added document: {file_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to add document {file_path}: {e}")
            return False
    
    async def search_documents(self, query: str, context_limit: int = 3) -> List[str]:
        """Search for relevant document content"""
        if not self.enabled:
            return []
        
        try:
            results = await self.vector_store.search(query, context_limit)
            return [result['content'] for result in results]
            
        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []
    
    async def get_context_for_query(self, query: str, conversation_history: List[Dict] = None) -> str:
        """Get contextual information for a query"""
        if not self.enabled:
            return ""
        
        try:
            # Search for relevant documents
            relevant_docs = await self.search_documents(query, context_limit=3)
            
            if not relevant_docs:
                return ""
            
            # Format context
            context = "Based on the following relevant information:\n\n"
            for i, doc in enumerate(relevant_docs, 1):
                context += f"[Context {i}]: {doc.strip()}\n\n"
            
            context += "Please use this information to help answer the user's question.\n\n"
            return context
            
        except Exception as e:
            logger.error(f"Failed to get context for query: {e}")
            return ""
    
    async def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents in the knowledge base"""
        if not self.enabled:
            return []
        
        try:
            # This is a simplified version - in a full implementation,
            # we'd have a separate documents table
            stats = self.vector_store.get_stats()
            return [{
                'total_documents': stats.get('unique_documents', 0),
                'total_chunks': stats.get('total_chunks', 0),
                'embedding_coverage': stats.get('embedding_coverage', 0)
            }]
            
        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document from the RAG system"""
        if not self.enabled:
            return False
        
        return await self.vector_store.delete_document(document_id)
    
    def is_enabled(self) -> bool:
        """Check if RAG is enabled and ready"""
        return self.enabled
    
    def get_supported_formats(self) -> List[str]:
        """Get supported file formats"""
        return self.document_processor.get_supported_formats()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive RAG statistics"""
        base_stats = {
            'enabled': self.enabled,
            'embeddings_available': EMBEDDINGS_AVAILABLE,
            'pdf_support': PDF_SUPPORT,
            'supported_formats': self.get_supported_formats()
        }
        
        if self.enabled:
            base_stats.update(self.vector_store.get_stats())
        
        return base_stats

# Factory function for easy initialization
def create_rag_service(config: Dict[str, Any] = None) -> RAGService:
    """Create RAG service with configuration"""
    config = config or {}
    
    db_path = config.get('db_path', 'rag_vectors.db')
    model_name = config.get('model_name', 'all-MiniLM-L6-v2')
    
    return RAGService(db_path, model_name)

# Integration function for chat enhancement
async def enhance_chat_with_rag(query: str, rag_service: RAGService, conversation_history: List[Dict] = None) -> str:
    """Enhance chat query with RAG context"""
    if not rag_service.is_enabled():
        return query
    
    context = await rag_service.get_context_for_query(query, conversation_history)
    
    if context:
        enhanced_query = f"{context}\nUser question: {query}"
        logger.info(f"Enhanced query with RAG context ({len(context)} characters)")
        return enhanced_query
    
    return query