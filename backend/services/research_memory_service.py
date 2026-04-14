import sqlite3
from typing import Any, Dict, List, Optional


class ResearchMemoryService:
    """Own encrypted research-vault table access."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connection(self):
        return sqlite3.connect(self.db_path)

    async def initialize(self):
        conn = self._connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS research_vault_entries (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                source_ref TEXT,
                file_hash TEXT,
                content_hash TEXT,
                model_name TEXT,
                payload_encrypted BLOB NOT NULL,
                payload_sha256 TEXT NOT NULL,
                prev_entry_hash TEXT,
                entry_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_research_event_type ON research_vault_entries(event_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_research_created_at ON research_vault_entries(created_at)")
        conn.commit()
        conn.close()

    def fetch_recent_entries(self, limit: int = 120) -> List[Dict[str, Any]]:
        conn = self._connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, event_type, source_ref, file_hash, content_hash, model_name,
                   payload_encrypted, payload_sha256, prev_entry_hash, entry_hash, created_at
            FROM research_vault_entries
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "event_type": row[1],
                "source_ref": row[2],
                "file_hash": row[3],
                "content_hash": row[4],
                "model_name": row[5],
                "payload_encrypted": row[6],
                "payload_sha256": row[7],
                "prev_entry_hash": row[8],
                "entry_hash": row[9],
                "created_at": row[10],
            }
            for row in rows
        ]

    def latest_entry_hash(self) -> Optional[str]:
        conn = self._connection()
        cursor = conn.cursor()
        cursor.execute("SELECT entry_hash FROM research_vault_entries ORDER BY created_at DESC, rowid DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    async def append_entry(
        self,
        *,
        entry_id: str,
        event_type: str,
        source_ref: Optional[str],
        file_hash: Optional[str],
        content_hash: Optional[str],
        model_name: Optional[str],
        payload_encrypted: bytes,
        payload_sha256: str,
        prev_entry_hash: Optional[str],
        entry_hash: str,
        created_at: str,
    ) -> None:
        conn = self._connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO research_vault_entries (
                id, event_type, source_ref, file_hash, content_hash, model_name,
                payload_encrypted, payload_sha256, prev_entry_hash, entry_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                event_type,
                source_ref,
                file_hash,
                content_hash,
                model_name,
                payload_encrypted,
                payload_sha256,
                prev_entry_hash,
                entry_hash,
                created_at,
            ),
        )
        conn.commit()
        conn.close()

    def get_stats(self) -> Dict[str, Any]:
        conn = self._connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM research_vault_entries")
        total_entries = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM research_vault_entries WHERE event_type = 'archive_ingest'")
        archive_entries = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM research_vault_entries WHERE event_type = 'chat_exchange'")
        chat_entries = cursor.fetchone()[0]
        cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM research_vault_entries")
        oldest, newest = cursor.fetchone()
        conn.close()
        return {
            "total_entries": total_entries,
            "archive_entries": archive_entries,
            "chat_entries": chat_entries,
            "oldest_entry": oldest,
            "newest_entry": newest,
        }

    async def wipe(self) -> int:
        conn = self._connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM research_vault_entries")
        deleted_entries = cursor.fetchone()[0]
        cursor.execute("DELETE FROM research_vault_entries")
        conn.commit()
        conn.close()
        return deleted_entries
