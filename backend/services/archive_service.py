import hashlib
import json
import logging
import sqlite3
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class ArchiveService:
    """Longitudinal archive analysis pipeline for chat-history research."""

    def __init__(self, db_path: str, analysis_service=None, rag_service=None):
        self.db_path = db_path
        self.analysis_service = analysis_service
        self.rag_service = rag_service

    async def initialize(self):
        """Create archive-analysis tables and apply lightweight schema migrations."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS archive_documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                source_path TEXT NOT NULL,
                archive_type TEXT NOT NULL,
                retention_mode TEXT DEFAULT 'exact_reference',
                file_hash TEXT,
                content_hash TEXT,
                era_label TEXT,
                summary TEXT,
                personality_profile TEXT,
                themes TEXT,
                relationship_dynamics TEXT,
                model_observations TEXT,
                human_state TEXT,
                legal_sensitivity INTEGER DEFAULT 0,
                should_influence_personality INTEGER DEFAULT 0,
                metadata TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS formative_moments (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                significance TEXT,
                tone TEXT,
                metadata TEXT,
                created_at TEXT
            )
            """
        )

        self._ensure_column(cursor, "archive_documents", "retention_mode", "TEXT DEFAULT 'exact_reference'")
        self._ensure_column(cursor, "archive_documents", "file_hash", "TEXT")
        self._ensure_column(cursor, "archive_documents", "content_hash", "TEXT")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_archive_type ON archive_documents(archive_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_era_label ON archive_documents(era_label)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_retention_mode ON archive_documents(retention_mode)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_hash ON archive_documents(file_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_hash ON archive_documents(content_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_formative_document_id ON formative_moments(document_id)")

        conn.commit()
        conn.close()

    def _ensure_column(self, cursor, table_name: str, column_name: str, column_sql: str):
        existing = {
            row[1]
            for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in existing:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    def compute_hashes(
        self,
        text: str,
        raw_bytes: Optional[bytes] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Optional[str]]:
        """Compute proof-oriented hashes without retaining source text."""
        metadata = metadata or {}
        normalized_text = " ".join(text.split()).strip()

        file_hash = metadata.get("file_hash")
        if not file_hash and raw_bytes is not None:
            file_hash = hashlib.sha256(raw_bytes).hexdigest()

        content_hash = metadata.get("content_hash")
        if not content_hash and normalized_text:
            content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

        return {
            "file_hash": file_hash,
            "content_hash": content_hash,
        }

    def find_duplicate(
        self,
        *,
        file_hash: Optional[str],
        content_hash: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Return an existing record when the same file or normalized content was already imported."""
        if not file_hash and not content_hash:
            return None

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if content_hash:
            cursor.execute(
                """
                SELECT id, filename, archive_type, retention_mode, updated_at
                FROM archive_documents
                WHERE content_hash = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (content_hash,),
            )
            row = cursor.fetchone()
            if row:
                conn.close()
                return {
                    "id": row[0],
                    "filename": row[1],
                    "archive_type": row[2],
                    "retention_mode": row[3],
                    "updated_at": row[4],
                    "match_type": "content_hash",
                }

        if file_hash:
            cursor.execute(
                """
                SELECT id, filename, archive_type, retention_mode, updated_at
                FROM archive_documents
                WHERE file_hash = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (file_hash,),
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                return {
                    "id": row[0],
                    "filename": row[1],
                    "archive_type": row[2],
                    "retention_mode": row[3],
                    "updated_at": row[4],
                    "match_type": "file_hash",
                }

        conn.close()
        return None

    def classify_document(self, filename: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Heuristically classify an uploaded archive file."""
        metadata = metadata or {}
        if metadata.get("archive_type"):
            return {
                "archive_type": metadata["archive_type"],
                "archive_like": metadata["archive_type"] in {"archive_chat", "mixed_archive"},
                "legal_sensitivity": bool(metadata.get("legal_sensitivity")),
                "technical_density": int(metadata.get("technical_density", 0)),
                "emotional_density": int(metadata.get("emotional_density", 0)),
            }

        lowered = text.lower()
        filename_lower = filename.lower()

        conversational_markers = ["user:", "assistant:", "human:", "ai:", "me:", "you:"]
        legal_markers = [
            "lawsuit",
            "complaint",
            "plaintiff",
            "defendant",
            "motion",
            "court",
            "order",
            "hearing",
            "statute",
            "legal",
            "attorney",
            "lawyer",
            "divorce",
            "deadline",
            "evidence",
            "compliance",
        ]
        technical_markers = ["code", "python", "bug", "function", "class", "api", "git", "database"]
        emotional_markers = ["love", "hurt", "alone", "afraid", "miss", "trust", "withdrew", "value"]

        convo_hits = sum(lowered.count(marker) for marker in conversational_markers)
        legal_hits = sum(lowered.count(marker) for marker in legal_markers)
        tech_hits = sum(lowered.count(marker) for marker in technical_markers)
        emotional_hits = sum(lowered.count(marker) for marker in emotional_markers)

        archive_like = any(
            keyword in filename_lower
            for keyword in ["archive", "chat", "conversation", "messages", "transcript", "dialogue"]
        ) or convo_hits >= 4

        if archive_like and legal_hits >= 6 and convo_hits < 4:
            archive_type = "legal_reference"
        elif archive_like and legal_hits >= 4:
            archive_type = "mixed_archive"
        elif archive_like:
            archive_type = "archive_chat"
        elif legal_hits >= 3:
            archive_type = "legal_reference"
        else:
            archive_type = "reference_document"

        return {
            "archive_type": archive_type,
            "archive_like": archive_like,
            "legal_sensitivity": legal_hits >= 3,
            "technical_density": tech_hits,
            "emotional_density": emotional_hits,
        }

    def default_analysis(
        self,
        filename: str,
        classification: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fallback analysis when LLM archive analysis is unavailable."""
        metadata = metadata or {}
        archive_type = classification["archive_type"]
        era_label = metadata.get("era_label") or {
            "archive_chat": "General archive era",
            "mixed_archive": "Mixed archive / legal overlap era",
            "legal_reference": "Legal reference lane",
            "reference_document": "Reference lane",
        }[archive_type]

        return {
            "archive_type": archive_type,
            "era_label": era_label,
            "summary": f"Imported {archive_type.replace('_', ' ')} from {filename}.",
            "personality_profile": "",
            "themes": [],
            "relationship_dynamics": [],
            "model_observations": [],
            "human_state": [],
            "legal_sensitivity": classification["legal_sensitivity"],
            "should_influence_personality": archive_type == "archive_chat" and not classification["legal_sensitivity"],
            "formative_moments": [],
        }

    async def analyze_document(
        self,
        filename: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run archive analysis, preferring the configured local/cloud analysis service when available."""
        classification = self.classify_document(filename, text, metadata)
        analysis = self.default_analysis(filename, classification, metadata)

        if not self.analysis_service:
            return analysis

        if classification["archive_type"] not in {"archive_chat", "mixed_archive", "legal_reference"}:
            return analysis

        try:
            ai_analysis = await self.analysis_service.analyze_archive_document(
                text=text,
                filename=filename,
                archive_type=classification["archive_type"],
            )
            if not ai_analysis:
                return analysis

            analysis.update(ai_analysis)
            analysis["archive_type"] = ai_analysis.get("archive_type", analysis["archive_type"])
            analysis["legal_sensitivity"] = bool(
                ai_analysis.get("legal_sensitivity", analysis["legal_sensitivity"])
            )
            requested_personality_influence = bool(
                ai_analysis.get("should_influence_personality", analysis["should_influence_personality"])
            )
            analysis["should_influence_personality"] = (
                requested_personality_influence and not analysis["legal_sensitivity"]
            )
            return analysis
        except Exception as e:
            logger.error(f"Archive analysis failed for {filename}: {e}")
            return analysis

    def select_retention_mode(self, analysis: Dict[str, Any]) -> str:
        """Choose whether raw text is retained for exact retrieval or discarded after distillation."""
        archive_type = analysis.get("archive_type", "reference_document")
        legal_sensitivity = bool(analysis.get("legal_sensitivity"))

        if archive_type == "archive_chat" and not legal_sensitivity:
            return "distill_only"
        if archive_type == "mixed_archive":
            return "exact_reference" if legal_sensitivity else "distill_only"
        return "exact_reference"

    def apply_manual_direction(
        self,
        analysis: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Allow the user to override automatic routing for specific files."""
        metadata = metadata or {}
        manual_direction = (metadata.get("manual_direction") or "auto").strip().lower()
        updated = dict(analysis)

        if manual_direction == "personality":
            updated["archive_type"] = "archive_chat"
            updated["retention_mode"] = "distill_only"
            updated["legal_sensitivity"] = False
            updated["should_influence_personality"] = True
        elif manual_direction == "reference":
            updated["retention_mode"] = "exact_reference"
            updated["should_influence_personality"] = False

        updated["manual_direction"] = manual_direction
        return updated

    async def prepare_document(
        self,
        *,
        filename: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        raw_bytes: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """Analyze retention, hashes, and duplicate status before storage."""
        metadata = metadata or {}
        hashes = self.compute_hashes(text, raw_bytes=raw_bytes, metadata=metadata)
        duplicate = self.find_duplicate(
            file_hash=hashes.get("file_hash"),
            content_hash=hashes.get("content_hash"),
        )
        analysis = await self.analyze_document(
            filename,
            text,
            {
                **metadata,
                **hashes,
            },
        )
        analysis = self.apply_manual_direction(analysis, metadata)
        retention_mode = metadata.get("retention_mode") or analysis.get("retention_mode") or self.select_retention_mode(analysis)

        return {
            "analysis": analysis,
            "retention_mode": retention_mode,
            "file_hash": hashes.get("file_hash"),
            "content_hash": hashes.get("content_hash"),
            "duplicate": duplicate,
        }

    async def process_document(
        self,
        file_path: str,
        filename: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        precomputed: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Analyze, store, and optionally distill a document into personality memory."""
        metadata = metadata or {}
        prepared = precomputed or await self.prepare_document(filename=filename, text=text, metadata=metadata)
        analysis = prepared["analysis"]
        retention_mode = prepared["retention_mode"]
        file_hash = prepared.get("file_hash")
        content_hash = prepared.get("content_hash")
        duplicate = prepared.get("duplicate")

        if duplicate:
            return {
                **analysis,
                "archive_document_created": False,
                "personality_memory_created": False,
                "formative_moments_created": 0,
                "retention_mode": retention_mode,
                "file_hash": file_hash,
                "content_hash": content_hash,
                "skipped_duplicate": True,
                "duplicate_of": duplicate,
            }

        document_id = hashlib.md5(f"{filename}:{content_hash or text[:500]}".encode()).hexdigest()
        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO archive_documents (
                id, filename, source_path, archive_type, retention_mode, file_hash, content_hash,
                era_label, summary, personality_profile, themes, relationship_dynamics, model_observations,
                human_state, legal_sensitivity, should_influence_personality, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM archive_documents WHERE id = ?), ?), ?)
            """,
            (
                document_id,
                filename,
                file_path,
                analysis.get("archive_type", "reference_document"),
                retention_mode,
                file_hash,
                content_hash,
                analysis.get("era_label"),
                analysis.get("summary"),
                analysis.get("personality_profile", ""),
                json.dumps(analysis.get("themes", [])),
                json.dumps(analysis.get("relationship_dynamics", [])),
                json.dumps(analysis.get("model_observations", [])),
                json.dumps(analysis.get("human_state", [])),
                1 if analysis.get("legal_sensitivity") else 0,
                1 if analysis.get("should_influence_personality") else 0,
                json.dumps({**metadata, "retention_mode": retention_mode}),
                document_id,
                now,
                now,
            ),
        )

        cursor.execute("DELETE FROM formative_moments WHERE document_id = ?", (document_id,))
        formative_moments = analysis.get("formative_moments", [])
        for index, moment in enumerate(formative_moments):
            moment_id = hashlib.md5(f"{document_id}:{index}:{moment.get('title', '')}".encode()).hexdigest()
            cursor.execute(
                """
                INSERT OR REPLACE INTO formative_moments
                (id, document_id, title, summary, significance, tone, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    moment_id,
                    document_id,
                    moment.get("title", f"Moment {index + 1}"),
                    moment.get("summary", ""),
                    moment.get("significance"),
                    moment.get("tone"),
                    json.dumps(moment),
                    now,
                ),
            )

        conn.commit()
        conn.close()

        personality_memory_created = False
        if (
            self.rag_service
            and retention_mode == "distill_only"
            and analysis.get("should_influence_personality")
            and not analysis.get("legal_sensitivity")
            and analysis.get("personality_profile", "").strip()
        ):
            personality_memory_created = await self.rag_service.save_persona_memory(
                source=file_path,
                filename=filename,
                content=analysis["personality_profile"],
                metadata={
                    **metadata,
                    "archive_type": analysis.get("archive_type"),
                    "era_label": analysis.get("era_label"),
                    "retention_mode": retention_mode,
                    "file_hash": file_hash,
                    "content_hash": content_hash,
                    "source_kind": "archive_personality_distillation",
                },
            )

        return {
            **analysis,
            "archive_document_created": True,
            "personality_memory_created": personality_memory_created,
            "formative_moments_created": len(formative_moments),
            "retention_mode": retention_mode,
            "file_hash": file_hash,
            "content_hash": content_hash,
            "skipped_duplicate": False,
        }

    async def delete_document(self, document_id: str) -> Dict[str, Any]:
        """Delete an archive document plus any RAG/persona material derived from it."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, filename, source_path, archive_type, retention_mode, file_hash, content_hash
            FROM archive_documents
            WHERE id = ?
            """,
            (document_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"deleted": False, "reason": "not_found"}

        record = {
            "id": row[0],
            "filename": row[1],
            "source_path": row[2],
            "archive_type": row[3],
            "retention_mode": row[4],
            "file_hash": row[5],
            "content_hash": row[6],
        }

        cursor.execute("DELETE FROM formative_moments WHERE document_id = ?", (document_id,))
        deleted_moments = cursor.rowcount
        cursor.execute("DELETE FROM archive_documents WHERE id = ?", (document_id,))
        deleted_archive_rows = cursor.rowcount
        conn.commit()
        conn.close()

        deleted_rag_chunks = 0
        deleted_persona_memories = 0
        if self.rag_service:
            if record["content_hash"]:
                deleted_rag_chunks = await self.rag_service.delete_documents_by_content_hash(record["content_hash"])
                deleted_persona_memories = await self.rag_service.delete_persona_memories(
                    source=record["source_path"],
                    filename=record["filename"],
                    content_hash=record["content_hash"],
                )
            else:
                deleted_persona_memories = await self.rag_service.delete_persona_memories(
                    source=record["source_path"],
                    filename=record["filename"],
                )

        return {
            "deleted": deleted_archive_rows > 0,
            "document_id": document_id,
            "filename": record["filename"],
            "archive_type": record["archive_type"],
            "retention_mode": record["retention_mode"],
            "deleted_archive_rows": deleted_archive_rows,
            "deleted_formative_moments": deleted_moments,
            "deleted_rag_chunks": deleted_rag_chunks,
            "deleted_persona_memories": deleted_persona_memories,
            "research_vault_unchanged": True,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate archive-analysis statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM archive_documents")
        total_documents = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM formative_moments")
        total_formative_moments = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT era_label) FROM archive_documents WHERE era_label IS NOT NULL AND era_label != ''")
        total_eras = cursor.fetchone()[0]

        cursor.execute("SELECT archive_type, COUNT(*) FROM archive_documents GROUP BY archive_type")
        type_counts = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT retention_mode, COUNT(*) FROM archive_documents GROUP BY retention_mode")
        retention_counts = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) FROM archive_documents WHERE legal_sensitivity = 1")
        legal_sensitive_documents = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM archive_documents WHERE should_influence_personality = 1")
        personality_documents = cursor.fetchone()[0]

        conn.close()

        return {
            "total_documents": total_documents,
            "total_eras": total_eras,
            "total_formative_moments": total_formative_moments,
            "legal_sensitive_documents": legal_sensitive_documents,
            "personality_documents": personality_documents,
            "type_counts": type_counts,
            "retention_counts": retention_counts,
        }

    async def list_documents(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return stored archive-analysis documents."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, filename, archive_type, retention_mode, file_hash, content_hash, era_label, summary,
                   legal_sensitivity, should_influence_personality, updated_at
            FROM archive_documents
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
                "filename": row[1],
                "archive_type": row[2],
                "retention_mode": row[3],
                "file_hash": row[4],
                "content_hash": row[5],
                "era_label": row[6],
                "summary": row[7],
                "legal_sensitivity": bool(row[8]),
                "should_influence_personality": bool(row[9]),
                "updated_at": row[10],
            }
            for row in rows
        ]

    async def list_formative_moments(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return preserved formative moments across archive docs."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT fm.id, ad.filename, ad.era_label, fm.title, fm.summary, fm.significance, fm.tone, fm.created_at
            FROM formative_moments fm
            JOIN archive_documents ad ON ad.id = fm.document_id
            ORDER BY fm.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": row[0],
                "filename": row[1],
                "era_label": row[2],
                "title": row[3],
                "summary": row[4],
                "significance": row[5],
                "tone": row[6],
                "created_at": row[7],
            }
            for row in rows
        ]

    async def list_eras(self) -> List[Dict[str, Any]]:
        """Return grouped era summaries derived from analyzed documents."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT era_label, filename, archive_type, summary, themes, updated_at
            FROM archive_documents
            WHERE era_label IS NOT NULL AND era_label != ''
            ORDER BY updated_at DESC
            """
        )
        rows = cursor.fetchall()
        conn.close()

        grouped: Dict[str, Dict[str, Any]] = {}
        for era_label, filename, archive_type, summary, themes_json, updated_at in rows:
            group = grouped.setdefault(
                era_label,
                {
                    "era_label": era_label,
                    "document_count": 0,
                    "archive_types": Counter(),
                    "filenames": [],
                    "summaries": [],
                    "theme_counter": Counter(),
                    "updated_at": updated_at,
                },
            )
            group["document_count"] += 1
            group["archive_types"][archive_type] += 1
            group["filenames"].append(filename)
            if summary:
                group["summaries"].append(summary)
            for theme in json.loads(themes_json or "[]"):
                group["theme_counter"][theme] += 1

        results = []
        for group in grouped.values():
            results.append(
                {
                    "era_label": group["era_label"],
                    "document_count": group["document_count"],
                    "archive_types": dict(group["archive_types"]),
                    "filenames": group["filenames"][:10],
                    "top_themes": [theme for theme, _ in group["theme_counter"].most_common(6)],
                    "summary_excerpt": group["summaries"][0] if group["summaries"] else "",
                    "updated_at": group["updated_at"],
                }
            )

        results.sort(key=lambda item: item["document_count"], reverse=True)
        return results
