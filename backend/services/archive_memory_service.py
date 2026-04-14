import json
import sqlite3
from collections import Counter
from typing import Any, Dict, List, Optional


class ArchiveMemoryService:
    """Own archive-document and formative-moment table access."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connection(self):
        return sqlite3.connect(self.db_path)

    async def initialize(self):
        conn = self._connection()
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
        existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if column_name not in existing:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    def find_duplicate(self, *, file_hash: Optional[str], content_hash: Optional[str]) -> Optional[Dict[str, Any]]:
        if not file_hash and not content_hash:
            return None

        conn = self._connection()
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

    async def upsert_document(
        self,
        *,
        document_id: str,
        filename: str,
        source_path: str,
        archive_type: str,
        retention_mode: str,
        file_hash: Optional[str],
        content_hash: Optional[str],
        era_label: Optional[str],
        summary: Optional[str],
        personality_profile: str,
        themes: List[str],
        relationship_dynamics: List[str],
        model_observations: List[str],
        human_state: List[str],
        legal_sensitivity: bool,
        should_influence_personality: bool,
        metadata: Dict[str, Any],
        now: str,
    ) -> None:
        conn = self._connection()
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
                source_path,
                archive_type,
                retention_mode,
                file_hash,
                content_hash,
                era_label,
                summary,
                personality_profile,
                json.dumps(themes),
                json.dumps(relationship_dynamics),
                json.dumps(model_observations),
                json.dumps(human_state),
                1 if legal_sensitivity else 0,
                1 if should_influence_personality else 0,
                json.dumps(metadata),
                document_id,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()

    async def replace_formative_moments(self, document_id: str, formative_moments: List[Dict[str, Any]], now: str, id_factory) -> None:
        conn = self._connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM formative_moments WHERE document_id = ?", (document_id,))
        for index, moment in enumerate(formative_moments):
            cursor.execute(
                """
                INSERT OR REPLACE INTO formative_moments
                (id, document_id, title, summary, significance, tone, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id_factory(index, moment),
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

    async def fetch_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connection()
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
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "filename": row[1],
            "source_path": row[2],
            "archive_type": row[3],
            "retention_mode": row[4],
            "file_hash": row[5],
            "content_hash": row[6],
        }

    async def delete_document_record(self, document_id: str) -> Dict[str, int]:
        conn = self._connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM formative_moments WHERE document_id = ?", (document_id,))
        deleted_moments = cursor.rowcount
        cursor.execute("DELETE FROM archive_documents WHERE id = ?", (document_id,))
        deleted_archive_rows = cursor.rowcount
        conn.commit()
        conn.close()
        return {
            "deleted_formative_moments": deleted_moments,
            "deleted_archive_rows": deleted_archive_rows,
        }

    def get_stats(self) -> Dict[str, Any]:
        conn = self._connection()
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
        conn = self._connection()
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
        conn = self._connection()
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
        conn = self._connection()
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
