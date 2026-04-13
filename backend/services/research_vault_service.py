import hashlib
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

from config import config


logger = logging.getLogger(__name__)


class ResearchVaultService:
    """Encrypted append-only research vault with delete-only control."""

    def __init__(self, db_path: str = "rag_vectors.db"):
        self.db_path = db_path
        self.enabled = config.RESEARCH_VAULT_ENABLED
        self._fernet: Optional[Fernet] = None

    async def initialize(self):
        if not self.enabled:
            return

        self._fernet = Fernet(self._load_or_create_key())

        conn = sqlite3.connect(self.db_path)
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

    def _load_or_create_key(self) -> bytes:
        if config.RESEARCH_VAULT_KEY:
            return config.RESEARCH_VAULT_KEY.encode("utf-8")

        key_path = self._resolve_key_path()
        if os.path.exists(key_path):
            with open(key_path, "rb") as handle:
                return handle.read().strip()

        key = Fernet.generate_key()
        with open(key_path, "wb") as handle:
            handle.write(key)
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass
        return key

    def _resolve_key_path(self) -> Path:
        path = Path(config.RESEARCH_VAULT_KEY_FILE).expanduser()
        if path.is_absolute():
            return path
        return (Path(__file__).resolve().parent.parent / path).resolve()

    def _connection(self):
        return sqlite3.connect(self.db_path)

    def _latest_entry_hash(self, cursor) -> Optional[str]:
        cursor.execute(
            "SELECT entry_hash FROM research_vault_entries ORDER BY created_at DESC, rowid DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return row[0] if row else None

    async def append_entry(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        source_ref: Optional[str] = None,
        file_hash: Optional[str] = None,
        content_hash: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> Optional[str]:
        if not self.enabled or not self._fernet:
            return None

        created_at = datetime.now().isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        payload_sha256 = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        encrypted = self._fernet.encrypt(payload_json.encode("utf-8"))
        entry_id = str(uuid.uuid4())

        conn = self._connection()
        cursor = conn.cursor()
        prev_hash = self._latest_entry_hash(cursor)
        entry_hash_material = "|".join(
            [
                entry_id,
                event_type,
                source_ref or "",
                file_hash or "",
                content_hash or "",
                model_name or "",
                payload_sha256,
                prev_hash or "",
                created_at,
            ]
        )
        entry_hash = hashlib.sha256(entry_hash_material.encode("utf-8")).hexdigest()

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
                encrypted,
                payload_sha256,
                prev_hash,
                entry_hash,
                created_at,
            ),
        )
        conn.commit()
        conn.close()
        return entry_id

    def get_stats(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}

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
            "enabled": True,
            "total_entries": total_entries,
            "archive_entries": archive_entries,
            "chat_entries": chat_entries,
            "oldest_entry": oldest,
            "newest_entry": newest,
        }

    async def wipe(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "deleted_entries": 0}

        conn = self._connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM research_vault_entries")
        deleted_entries = cursor.fetchone()[0]
        cursor.execute("DELETE FROM research_vault_entries")
        conn.commit()
        conn.close()
        return {"enabled": True, "deleted_entries": deleted_entries}
