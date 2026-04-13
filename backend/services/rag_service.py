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
import re
from typing import List, Dict, Optional, Any, Union
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod
from config import config

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

try:
    from docx import Document as DocxDocument
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False

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
    
    def __init__(self, chunk_size: int = 1400, chunk_overlap: int = 250, min_chunk_size: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    async def process_document(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Process document and return chunks"""
        try:
            file_path_obj = Path(file_path)
            
            if not file_path_obj.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Extract text based on file type
            if file_path_obj.suffix.lower() == '.pdf':
                text = await self._extract_pdf_text(file_path_obj)
            elif file_path_obj.suffix.lower() == '.docx':
                text = await self._extract_docx_text(file_path_obj)
            elif file_path_obj.suffix.lower() in ['.txt', '.md']:
                text = await self._extract_text_file(file_path_obj)
            else:
                raise ValueError(f"Unsupported file format: {file_path_obj.suffix}")
            
            # Create chunks
            chunks = self._create_chunks(self._normalize_text(text))
            
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

    async def process_text(self, text: str, source: str, metadata: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Process raw text into chunks without requiring a file on disk."""
        try:
            normalized_text = self._normalize_text(text)
            chunks = self._create_chunks(normalized_text)
            if not chunks:
                return []

            doc_id = hashlib.md5(f"{source}:{normalized_text[:100]}".encode()).hexdigest()
            document_chunks = []

            for i, chunk in enumerate(chunks):
                document_chunks.append({
                    'id': hashlib.md5(f"{doc_id}:{i}:{chunk}".encode()).hexdigest(),
                    'document_id': doc_id,
                    'content': chunk,
                    'metadata': {
                        **(metadata or {}),
                        'source': source,
                        'chunk_index': i,
                        'total_chunks': len(chunks)
                    },
                    'created_at': datetime.now().isoformat()
                })

            logger.info(f"Processed text source {source}: {len(chunks)} chunks")
            return document_chunks
        except Exception as e:
            logger.error(f"Failed to process text source {source}: {e}")
            return []

    async def extract_text(self, file_path: str) -> str:
        """Extract raw text for classification/distillation."""
        file_path_obj = Path(file_path)

        if file_path_obj.suffix.lower() == '.pdf':
            return self._normalize_text(await self._extract_pdf_text(file_path_obj))
        if file_path_obj.suffix.lower() == '.docx':
            return self._normalize_text(await self._extract_docx_text(file_path_obj))
        if file_path_obj.suffix.lower() in ['.txt', '.md']:
            return self._normalize_text(await self._extract_text_file(file_path_obj))

        raise ValueError(f"Unsupported file format: {file_path_obj.suffix}")
    
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

    async def _extract_docx_text(self, file_path: Path) -> str:
        """Extract text from DOCX file"""
        if not DOCX_SUPPORT:
            raise ImportError("python-docx not available for DOCX processing")

        try:
            document = DocxDocument(file_path)
            paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
            return "\n\n".join(paragraphs)
        except Exception as e:
            logger.error(f"Failed to read DOCX file: {e}")
            raise

    def _normalize_text(self, text: str) -> str:
        """Normalize whitespace before chunking."""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        normalized = re.sub(r"[ \t]+", " ", normalized)
        return normalized.strip()

    def _split_into_segments(self, text: str) -> List[str]:
        """Split content into paragraph- and sentence-aware segments."""
        paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n+", text) if paragraph.strip()]
        segments: List[str] = []

        for paragraph in paragraphs:
            if len(paragraph) <= self.chunk_size:
                segments.append(paragraph)
                continue

            sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", paragraph)
                if sentence.strip()
            ]

            if not sentences:
                sentences = [paragraph]

            current = []
            current_len = 0
            for sentence in sentences:
                sentence_len = len(sentence) + (1 if current else 0)
                if current and current_len + sentence_len > self.chunk_size:
                    segments.append(" ".join(current))
                    current = [sentence]
                    current_len = len(sentence)
                else:
                    current.append(sentence)
                    current_len += sentence_len

            if current:
                segments.append(" ".join(current))

        return segments

    def _build_overlap(self, segments: List[str]) -> List[str]:
        """Keep a trailing overlap window to improve retrieval continuity."""
        overlap_segments: List[str] = []
        overlap_len = 0

        for segment in reversed(segments):
            overlap_segments.insert(0, segment)
            overlap_len += len(segment) + 1
            if overlap_len >= self.chunk_overlap:
                break

        return overlap_segments
    
    def _create_chunks(self, text: str) -> List[str]:
        """Split text into paragraph-aware overlapping chunks."""
        if not text.strip():
            return []

        segments = self._split_into_segments(text)
        chunks: List[str] = []
        current_segments: List[str] = []
        current_len = 0

        for segment in segments:
            segment_len = len(segment) + (2 if current_segments else 0)
            if current_segments and current_len + segment_len > self.chunk_size:
                chunk = "\n\n".join(current_segments).strip()
                if chunk:
                    chunks.append(chunk)

                current_segments = self._build_overlap(current_segments)
                current_len = len("\n\n".join(current_segments))

            current_segments.append(segment)
            current_len = len("\n\n".join(current_segments))

        if current_segments:
            chunks.append("\n\n".join(current_segments).strip())

        filtered_chunks: List[str] = []
        for chunk in chunks:
            if filtered_chunks and len(chunk) < self.min_chunk_size:
                filtered_chunks[-1] = f"{filtered_chunks[-1]}\n\n{chunk}".strip()
            else:
                filtered_chunks.append(chunk)

        deduped_chunks: List[str] = []
        seen = set()
        for chunk in filtered_chunks:
            key = hashlib.md5(chunk.encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                deduped_chunks.append(chunk)

        return deduped_chunks
    
    def get_supported_formats(self) -> List[str]:
        """Return supported file formats"""
        formats = [".txt", ".md"]
        if PDF_SUPPORT:
            formats.append(".pdf")
        if DOCX_SUPPORT:
            formats.append(".docx")
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
                self.model = SentenceTransformer(
                    model_name,
                    local_files_only=config.EMBEDDING_LOCAL_ONLY,
                )
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

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS persona_memories (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT,
                    updated_at TEXT
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
                return await self._hybrid_search(query, top_k)
            return await self._keyword_search(query, top_k)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def _hybrid_search(self, query: str, top_k: int) -> List[Dict]:
        """Combine vector and keyword search for more stable retrieval."""
        vector_results = await self._vector_search(query, max(top_k * 4, 10))
        keyword_results = await self._keyword_search(query, max(top_k * 4, 10))

        combined: Dict[str, Dict[str, Any]] = {}

        for result in vector_results:
            combined[result['id']] = {
                **result,
                'vector_score': max(0.0, (result.get('similarity', 0.0) + 1.0) / 2.0),
                'keyword_score': 0.0,
            }

        for result in keyword_results:
            existing = combined.get(result['id'])
            if existing:
                existing['keyword_score'] = max(existing['keyword_score'], result.get('similarity', 0.0))
            else:
                combined[result['id']] = {
                    **result,
                    'vector_score': 0.0,
                    'keyword_score': result.get('similarity', 0.0),
                }

        ranked_results = []
        for result in combined.values():
            result['similarity'] = round(
                (0.8 * result.get('vector_score', 0.0)) + (0.2 * result.get('keyword_score', 0.0)),
                4,
            )
            ranked_results.append(result)

        ranked_results.sort(key=lambda x: x['similarity'], reverse=True)
        return ranked_results[:top_k]
    
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
            
            query_terms = [term for term in re.findall(r"\w+", query.lower()) if len(term) > 1]
            if not query_terms:
                return []
            like_conditions = []
            params = []
            
            for term in query_terms:
                like_conditions.append("LOWER(content) LIKE ?")
                params.append(f"%{term}%")
            
            where_clause = " OR ".join(like_conditions)
            
            cursor.execute(f"""
                SELECT id, document_id, content, metadata
                FROM vector_documents
                WHERE {where_clause}
                LIMIT ?
            """, params + [max(top_k * 4, 10)])
            
            results = []
            for row in cursor.fetchall():
                doc_id, document_id, content, metadata_str = row
                content_lower = content.lower()
                hits = sum(content_lower.count(term) for term in query_terms)
                similarity = min(1.0, hits / max(len(query_terms), 1))
                results.append({
                    'id': doc_id,
                    'document_id': document_id,
                    'content': content,
                    'metadata': json.loads(metadata_str),
                    'similarity': float(similarity)
                })
            
            conn.close()
            results.sort(key=lambda x: x['similarity'], reverse=True)
            return results[:top_k]
            
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

    async def delete_documents_by_content_hash(self, content_hash: str) -> int:
        """Delete chunks whose metadata points at a specific content hash."""
        if not content_hash:
            return 0

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, metadata FROM vector_documents")
            rows = cursor.fetchall()

            ids_to_delete = []
            for row_id, metadata_str in rows:
                try:
                    metadata = json.loads(metadata_str) if metadata_str else {}
                except Exception:
                    metadata = {}
                if metadata.get("content_hash") == content_hash:
                    ids_to_delete.append(row_id)

            deleted = 0
            if ids_to_delete:
                cursor.executemany("DELETE FROM vector_documents WHERE id = ?", [(row_id,) for row_id in ids_to_delete])
                deleted = cursor.rowcount
                conn.commit()

            conn.close()
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete document chunks for content hash {content_hash}: {e}")
            return 0
    
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

            cursor.execute("SELECT COUNT(*) FROM persona_memories")
            persona_memories = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_chunks': total_chunks,
                'unique_documents': unique_docs,
                'embedded_chunks': embedded_chunks,
                'embedding_coverage': embedded_chunks / total_chunks if total_chunks > 0 else 0,
                'persona_memories': persona_memories,
                'model': self.model_name if self.model else None
            }
            
        except Exception as e:
            logger.error(f"Failed to get vector store stats: {e}")
            return {}

    async def save_persona_memory(self, source: str, filename: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Upsert a distilled persona memory record."""
        try:
            memory_id = hashlib.md5(f"{source}:{filename}".encode()).hexdigest()
            now = datetime.now().isoformat()

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO persona_memories
                (id, source, filename, content, metadata, created_at, updated_at)
                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    COALESCE((SELECT created_at FROM persona_memories WHERE id = ?), ?),
                    ?
                )
                """,
                (
                    memory_id,
                    source,
                    filename,
                    content,
                    json.dumps(metadata or {}),
                    memory_id,
                    now,
                    now,
                ),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to save persona memory: {e}")
            return False

    async def get_persona_memories(self, limit: int = 3) -> List[Dict[str, Any]]:
        """Fetch the most recent persona memories."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, source, filename, content, metadata, updated_at
                FROM persona_memories
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            conn.close()

            return [
                {
                    "id": row[0],
                    "source": row[1],
                    "filename": row[2],
                    "content": row[3],
                    "metadata": json.loads(row[4]) if row[4] else {},
                    "updated_at": row[5],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to load persona memories: {e}")
            return []

    async def delete_persona_memories(
        self,
        *,
        source: Optional[str] = None,
        filename: Optional[str] = None,
        content_hash: Optional[str] = None,
    ) -> int:
        """Delete persona memories matching a source, filename, or content hash."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, source, filename, metadata FROM persona_memories")
            rows = cursor.fetchall()

            ids_to_delete = []
            for memory_id, memory_source, memory_filename, metadata_str in rows:
                try:
                    metadata = json.loads(metadata_str) if metadata_str else {}
                except Exception:
                    metadata = {}

                source_match = source and memory_source == source
                filename_match = filename and memory_filename == filename
                content_hash_match = content_hash and metadata.get("content_hash") == content_hash

                if source_match or filename_match or content_hash_match:
                    ids_to_delete.append(memory_id)

            deleted = 0
            if ids_to_delete:
                cursor.executemany("DELETE FROM persona_memories WHERE id = ?", [(memory_id,) for memory_id in ids_to_delete])
                deleted = cursor.rowcount
                conn.commit()

            conn.close()
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete persona memories: {e}")
            return 0

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

    async def add_text_document(self, text: str, source: str, metadata: Dict[str, Any] = None) -> bool:
        """Add pre-extracted text content to the RAG system."""
        if not self.enabled:
            logger.warning("RAG service is not enabled")
            return False

        try:
            chunks = await self.document_processor.process_text(text, source, metadata)
            if not chunks:
                logger.warning(f"No chunks generated from text source {source}")
                return False

            success = await self.vector_store.add_documents(chunks)
            if success:
                logger.info(f"✅ Successfully added text source: {source}")
            return success
        except Exception as e:
            logger.error(f"Failed to add text source {source}: {e}")
            return False

    async def extract_document_text(self, file_path: str) -> str:
        """Extract normalized text for downstream distillation/classification."""
        try:
            return await self.document_processor.extract_text(file_path)
        except AttributeError:
            file_path_obj = Path(file_path)
            if file_path_obj.suffix.lower() in ['.txt', '.md']:
                return file_path_obj.read_text(encoding='utf-8')
            return ""
        except Exception as e:
            logger.error(f"Failed to extract document text for persona distillation: {e}")
            return ""

    async def delete_documents_by_content_hash(self, content_hash: str) -> int:
        """Delete exact-reference chunks matching a content hash."""
        return await self.vector_store.delete_documents_by_content_hash(content_hash)

    async def delete_persona_memories(
        self,
        *,
        source: Optional[str] = None,
        filename: Optional[str] = None,
        content_hash: Optional[str] = None,
    ) -> int:
        """Delete persona-memory records matching a source, filename, or content hash."""
        return await self.vector_store.delete_persona_memories(
            source=source,
            filename=filename,
            content_hash=content_hash,
        )

    def should_distill_personality(self, file_path: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Heuristic gate for personality-memory extraction."""
        metadata = metadata or {}
        filename = (metadata.get("filename") or Path(file_path).name).lower()
        lowered = text.lower()

        archive_keywords = ["archive", "chat", "conversation", "messages", "transcript", "dialogue"]
        conversational_markers = ["user:", "assistant:", "human:", "ai:", "me:", "you:"]
        legal_markers = ["complaint", "plaintiff", "defendant", "statute", "motion", "lawsuit", "court"]

        marker_hits = sum(lowered.count(marker) for marker in conversational_markers)
        archive_like = any(keyword in filename for keyword in archive_keywords) or marker_hits >= 4
        legal_heavy = sum(lowered.count(marker) for marker in legal_markers) >= 6 and marker_hits < 3

        return archive_like and not legal_heavy

    async def save_persona_memory(self, source: str, filename: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Persist a distilled personality profile."""
        if not self.enabled or not content.strip():
            return False
        return await self.vector_store.save_persona_memory(source, filename, content.strip(), metadata)

    async def get_persona_context(self, limit: int = 2) -> str:
        """Return a compact behavioral memory block for prompting."""
        if not self.enabled:
            return ""

        memories = await self.vector_store.get_persona_memories(limit)
        if not memories:
            return ""

        lines = [
            "Background personality memory:",
            "Use this only to shape tone, continuity, and relational geography.",
            "Do not treat it as exact factual authority, and do not let legal/conflict material dominate the response.",
            "",
        ]

        for index, memory in enumerate(reversed(memories), start=1):
            lines.append(f"[Persona {index}] distilled from {memory['filename']}")
            lines.append(memory["content"])
            lines.append("")

        return "\n".join(lines).strip()
    
    async def search_documents(self, query: str, context_limit: int = 3) -> List[str]:
        """Search for relevant document content"""
        if not self.enabled:
            return []
        
        try:
            results = await self.vector_store.search(query, context_limit)
            return results
            
        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []

    def _build_retrieval_query(self, query: str, conversation_history: Optional[List[Dict]] = None) -> str:
        """Blend the current query with recent user context for retrieval."""
        if not conversation_history:
            return query

        recent_user_messages = [
            message["content"].strip()
            for message in conversation_history[-6:]
            if message.get("role") == "user" and message.get("content")
        ][-2:]

        if not recent_user_messages:
            return query

        return "\n".join(recent_user_messages + [query])

    def _format_sources(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert search results to source metadata for prompting and UI."""
        formatted_sources = []
        for index, result in enumerate(results, start=1):
            metadata = result.get("metadata", {})
            content = result.get("content", "").strip()
            snippet = content[:240].replace("\n", " ")
            if len(content) > 240:
                snippet += "..."

            formatted_sources.append({
                "source_id": str(index),
                "filename": metadata.get("filename") or Path(metadata.get("source", "document")).name,
                "source": metadata.get("source", ""),
                "chunk_index": int(metadata.get("chunk_index", 0)),
                "total_chunks": int(metadata.get("total_chunks", 1)),
                "similarity": float(result.get("similarity", 0.0)),
                "snippet": snippet,
                "content": content,
            })

        return formatted_sources

    async def get_context_for_query(self, query: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Get contextual information and source metadata for a query."""
        if not self.enabled:
            return {"context": "", "sources": []}
        
        try:
            retrieval_query = self._build_retrieval_query(query, conversation_history)
            relevant_docs = await self.search_documents(retrieval_query, context_limit=4)
            
            if not relevant_docs:
                return {"context": "", "sources": []}

            sources = self._format_sources(relevant_docs)
            
            context_lines = [
                "You have access to retrieved knowledge-base excerpts below.",
                "If you rely on them, cite the relevant source numbers inline like [1] or [2].",
                "If the answer is not supported by the retrieved sources, say that clearly.",
                "",
            ]

            for source in sources:
                context_lines.append(
                    f"[Source {source['source_id']}] {source['filename']} "
                    f"(chunk {source['chunk_index'] + 1}/{source['total_chunks']}, score {source['similarity']:.2f})"
                )
                context_lines.append(source["content"])
                context_lines.append("")

            context = "\n".join(context_lines).strip()
            return {"context": context, "sources": sources}
            
        except Exception as e:
            logger.error(f"Failed to get context for query: {e}")
            return {"context": "", "sources": []}
    
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
        return self.document_processor.get_supported_formats() + [".json"]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive RAG statistics"""
        base_stats = {
            'enabled': self.enabled,
            'embeddings_available': EMBEDDINGS_AVAILABLE,
            'pdf_support': PDF_SUPPORT,
            'docx_support': DOCX_SUPPORT,
            'supported_formats': self.get_supported_formats()
        }
        
        if self.enabled:
            base_stats.update(self.vector_store.get_stats())
        
        return base_stats

# Factory function for easy initialization
def create_rag_service(settings: Dict[str, Any] = None) -> RAGService:
    """Create RAG service with configuration"""
    settings = settings or {}
    
    db_path = settings.get('db_path', 'rag_vectors.db')
    model_name = settings.get('model_name', config.EMBEDDING_MODEL)
    
    return RAGService(db_path, model_name)

# Integration function for chat enhancement
async def enhance_chat_with_rag(query: str, rag_service: RAGService, conversation_history: List[Dict] = None) -> Dict[str, Any]:
    """Enhance chat query with RAG context and structured sources."""
    if not rag_service.is_enabled():
        return {"enhanced_query": query, "sources": []}
    
    context_result = await rag_service.get_context_for_query(query, conversation_history)
    context = context_result.get("context", "")
    sources = context_result.get("sources", [])
    
    if context:
        enhanced_query = f"{context}\nUser question: {query}"
        logger.info(f"Enhanced query with RAG context ({len(context)} characters)")
        return {"enhanced_query": enhanced_query, "sources": sources}
    
    return {"enhanced_query": query, "sources": []}
