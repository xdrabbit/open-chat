import hashlib
import json
import logging
import os
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet

from config import config
from .research_memory_service import ResearchMemoryService


logger = logging.getLogger(__name__)


class ResearchVaultService:
    """Encrypted append-only research vault with delete-only control."""

    def __init__(self, db_path: str = "rag_vectors.db"):
        self.db_path = db_path
        self.enabled = config.RESEARCH_VAULT_ENABLED
        self._fernet: Optional[Fernet] = None
        self.memory = ResearchMemoryService(db_path)

    async def initialize(self):
        if not self.enabled:
            return

        self._fernet = Fernet(self._load_or_create_key())

        await self.memory.initialize()

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

    def _decrypt_payload(self, encrypted_payload: bytes) -> Dict[str, Any]:
        if not self._fernet:
            return {}

        try:
            decrypted = self._fernet.decrypt(encrypted_payload)
            return json.loads(decrypted.decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to decrypt research vault entry: {e}")
            return {}

    def _compact_text(self, value: str, max_chars: int = 320) -> str:
        text = " ".join((value or "").split())
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3].rstrip() + "..."

    def _fetch_recent_entries(self, limit: int = 120) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        entries = []
        for row in self.memory.fetch_recent_entries(limit):
            entries.append(
                {
                    "id": row["id"],
                    "event_type": row["event_type"],
                    "source_ref": row["source_ref"],
                    "file_hash": row["file_hash"],
                    "content_hash": row["content_hash"],
                    "model_name": row["model_name"],
                    "payload": self._decrypt_payload(row["payload_encrypted"]),
                    "payload_sha256": row["payload_sha256"],
                    "prev_entry_hash": row["prev_entry_hash"],
                    "entry_hash": row["entry_hash"],
                    "created_at": row["created_at"],
                }
            )

        entries.reverse()
        return entries

    def build_report_context(self, limit: int = 120) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "stats": {"enabled": False},
                "entries_considered": 0,
                "chat_samples": [],
                "archive_samples": [],
            }

        entries = self._fetch_recent_entries(limit)
        stats = self.get_stats()
        if not entries:
            return {
                "enabled": True,
                "stats": stats,
                "entries_considered": 0,
                "chat_samples": [],
                "archive_samples": [],
                "aggregates": {
                    "providers": {},
                    "models": {},
                    "archive_types": {},
                    "eras": {},
                    "retention_modes": {},
                    "legal_sensitive_count": 0,
                    "persona_influence_count": 0,
                    "generated_image_count": 0,
                    "image_upload_count": 0,
                    "rag_augmented_chat_count": 0,
                },
            }

        provider_counts = Counter()
        model_counts = Counter()
        archive_type_counts = Counter()
        era_counts = Counter()
        retention_counts = Counter()
        legal_sensitive_count = 0
        persona_influence_count = 0
        generated_image_count = 0
        image_upload_count = 0
        rag_augmented_chat_count = 0

        chat_samples = []
        archive_samples = []

        for entry in entries:
            payload = entry["payload"]
            if entry["event_type"] == "chat_exchange":
                provider = payload.get("provider") or "unknown"
                model = payload.get("model") or entry["model_name"] or "unknown"
                provider_counts[provider] += 1
                model_counts[model] += 1
                if payload.get("generated_image"):
                    generated_image_count += 1
                if payload.get("image_uploaded"):
                    image_upload_count += 1
                if int(payload.get("rag_source_count") or 0) > 0:
                    rag_augmented_chat_count += 1

                if len(chat_samples) < 48:
                    chat_samples.append(
                        {
                            "timestamp": payload.get("timestamp") or entry["created_at"],
                            "provider": provider,
                            "model": model,
                            "cloud_text_only": bool(payload.get("cloud_text_only")),
                            "rag_source_count": int(payload.get("rag_source_count") or 0),
                            "generated_image": bool(payload.get("generated_image")),
                            "image_uploaded": bool(payload.get("image_uploaded")),
                            "user_message_excerpt": self._compact_text(payload.get("user_message", ""), 280),
                            "assistant_response_excerpt": self._compact_text(payload.get("assistant_response", ""), 280),
                        }
                    )
            elif entry["event_type"] == "archive_ingest":
                analysis = payload.get("analysis") or {}
                metadata = payload.get("metadata") or {}
                archive_type = analysis.get("archive_type") or metadata.get("archive_type") or "unknown"
                era_label = analysis.get("era_label") or metadata.get("era_label") or "Unlabeled"
                retention_mode = analysis.get("retention_mode") or metadata.get("retention_mode") or "unknown"

                archive_type_counts[archive_type] += 1
                era_counts[era_label] += 1
                retention_counts[retention_mode] += 1
                if analysis.get("legal_sensitivity"):
                    legal_sensitive_count += 1
                if analysis.get("personality_memory_created"):
                    persona_influence_count += 1

                if len(archive_samples) < 48:
                    archive_samples.append(
                        {
                            "timestamp": payload.get("timestamp") or entry["created_at"],
                            "filename": payload.get("filename") or payload.get("thread_filename") or metadata.get("filename") or "archive entry",
                            "source_kind": payload.get("source_kind") or "archive",
                            "archive_type": archive_type,
                            "era_label": era_label,
                            "retention_mode": retention_mode,
                            "legal_sensitivity": bool(analysis.get("legal_sensitivity")),
                            "summary": self._compact_text(analysis.get("summary", ""), 320),
                            "personality_profile": self._compact_text(analysis.get("personality_profile", ""), 320),
                            "themes": list(analysis.get("themes") or [])[:6],
                            "relationship_dynamics": list(analysis.get("relationship_dynamics") or [])[:6],
                            "model_observations": list(analysis.get("model_observations") or [])[:6],
                            "human_state": list(analysis.get("human_state") or [])[:6],
                            "formative_moments": list(analysis.get("formative_moments") or [])[:4],
                            "raw_excerpt": self._compact_text(payload.get("raw_text", ""), 420),
                        }
                    )

        return {
            "enabled": True,
            "stats": stats,
            "entries_considered": len(entries),
            "chat_samples": chat_samples,
            "archive_samples": archive_samples,
            "aggregates": {
                "providers": dict(provider_counts),
                "models": dict(model_counts),
                "archive_types": dict(archive_type_counts),
                "eras": dict(era_counts),
                "retention_modes": dict(retention_counts),
                "legal_sensitive_count": legal_sensitive_count,
                "persona_influence_count": persona_influence_count,
                "generated_image_count": generated_image_count,
                "image_upload_count": image_upload_count,
                "rag_augmented_chat_count": rag_augmented_chat_count,
            },
        }

    def build_report_fallback(self, report_context: Dict[str, Any], mode: str) -> Dict[str, Any]:
        stats = report_context.get("stats", {})
        aggregates = report_context.get("aggregates", {})
        archive_samples = report_context.get("archive_samples", [])
        chat_samples = report_context.get("chat_samples", [])

        top_eras = ", ".join(
            f"{name} ({count})" for name, count in list((aggregates.get("eras") or {}).items())[:4]
        ) or "none yet"
        top_archive_types = ", ".join(
            f"{name} ({count})" for name, count in list((aggregates.get("archive_types") or {}).items())[:4]
        ) or "none yet"
        top_models = ", ".join(
            f"{name} ({count})" for name, count in list((aggregates.get("models") or {}).items())[:4]
        ) or "none yet"

        brief = (
            f"Research vault contains {stats.get('total_entries', 0)} sealed entries. "
            f"Archive records: {stats.get('archive_entries', 0)}. Chat exchanges: {stats.get('chat_entries', 0)}. "
            f"Dominant archive lanes: {top_archive_types}. Dominant eras: {top_eras}. "
            f"Observed model usage: {top_models}. "
            f"Legal-sensitive archive count: {aggregates.get('legal_sensitive_count', 0)}. "
            f"Persona-shaping archive count: {aggregates.get('persona_influence_count', 0)}."
        )

        sections = {
            "current_state": brief,
            "archive_signal": [
                sample.get("summary")
                for sample in archive_samples[:3]
                if sample.get("summary")
            ],
            "recent_chat_signal": [
                sample.get("assistant_response_excerpt")
                for sample in chat_samples[-3:]
                if sample.get("assistant_response_excerpt")
            ],
        }

        if mode == "brief":
            return {"report": brief, "sections": sections}

        full_report = "\n\n".join(
            [
                brief,
                f"Retention modes: {aggregates.get('retention_modes', {}) or 'none yet'}.",
                f"Generated image events: {aggregates.get('generated_image_count', 0)}. "
                f"Image uploads: {aggregates.get('image_upload_count', 0)}. "
                f"RAG-augmented chat events: {aggregates.get('rag_augmented_chat_count', 0)}.",
                "Recent archive signals: " + (" | ".join(sections["archive_signal"]) or "none yet"),
                "Recent chat signals: " + (" | ".join(sections["recent_chat_signal"]) or "none yet"),
            ]
        )
        return {"report": full_report, "sections": sections}

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

        prev_hash = self.memory.latest_entry_hash()
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

        await self.memory.append_entry(
            entry_id=entry_id,
            event_type=event_type,
            source_ref=source_ref,
            file_hash=file_hash,
            content_hash=content_hash,
            model_name=model_name,
            payload_encrypted=encrypted,
            payload_sha256=payload_sha256,
            prev_entry_hash=prev_hash,
            entry_hash=entry_hash,
            created_at=created_at,
        )
        return entry_id

    def get_stats(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}

        return {"enabled": True, **self.memory.get_stats()}

    async def wipe(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "deleted_entries": 0}

        deleted_entries = await self.memory.wipe()
        return {"enabled": True, "deleted_entries": deleted_entries}
