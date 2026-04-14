import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict


class IngestOrchestrator:
    """Own archive upload parsing, retention routing, and research side effects."""

    def __init__(self, rag_service, archive_service, research_vault_service, policy_service, chatgpt_parser: Callable):
        self.rag_service = rag_service
        self.archive_service = archive_service
        self.research_vault_service = research_vault_service
        self.policy_service = policy_service
        self.chatgpt_parser = chatgpt_parser

    async def handle_upload(self, file, ingest_intent: str) -> Dict:
        temp_file_path = None
        try:
            if not self.rag_service.is_enabled():
                raise RuntimeError("RAG service is not available")

            if not file.filename:
                raise ValueError("No filename provided")

            supported_formats = self.rag_service.get_supported_formats()
            file_extension = f".{file.filename.split('.')[-1].lower()}"
            if file_extension not in supported_formats:
                raise ValueError(f"Unsupported file format. Supported: {', '.join(supported_formats)}")

            normalized_ingest_intent = self.policy_service.normalize_ingest_intent(ingest_intent)

            temp_dir = "temp_documents"
            os.makedirs(temp_dir, exist_ok=True)
            safe_filename = Path(file.filename).name
            temp_file_path = os.path.join(temp_dir, safe_filename)

            with open(temp_file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            upload_file_hash = hashlib.sha256(content).hexdigest()
            upload_metadata = {
                "filename": file.filename,
                "content_type": file.content_type,
                "upload_time": datetime.now().isoformat(),
                "file_hash": upload_file_hash,
                "manual_direction": normalized_ingest_intent,
            }

            if file_extension == ".json":
                return await self._handle_chatgpt_export(
                    file=file,
                    temp_file_path=temp_file_path,
                    safe_filename=safe_filename,
                    upload_file_hash=upload_file_hash,
                    upload_metadata=upload_metadata,
                    normalized_ingest_intent=normalized_ingest_intent,
                )

            return await self._handle_single_document(
                file=file,
                content=content,
                temp_file_path=temp_file_path,
                upload_metadata=upload_metadata,
                normalized_ingest_intent=normalized_ingest_intent,
            )
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    async def _handle_chatgpt_export(
        self,
        *,
        file,
        temp_file_path: str,
        safe_filename: str,
        upload_file_hash: str,
        upload_metadata: Dict,
        normalized_ingest_intent: str,
    ) -> Dict:
        threads = self.chatgpt_parser(temp_file_path)
        if not threads:
            raise ValueError("Unsupported JSON file. Expected a ChatGPT conversations export.")

        imported_threads = 0
        skipped_duplicates = 0
        personality_memory_count = 0
        archive_document_count = 0
        formative_moments_count = 0
        legal_sensitive_threads = 0
        retention_counts = {"distill_only": 0, "exact_reference": 0}

        for thread in threads:
            thread_source = f"{safe_filename}::{thread['thread_filename']}"
            thread_metadata = {
                **upload_metadata,
                "source_kind": "chatgpt_export_thread",
                "conversation_title": thread["title"],
                "archive_type": thread["archive_type"],
                "legal_sensitivity": thread["legal_sensitivity"],
                "era_label": thread["era_label"],
                "message_count": thread["message_count"],
                "evidence_count": thread["evidence_count"],
                "participants": thread["participants"],
                "create_time": thread["create_time"],
                "update_time": thread["update_time"],
                "legal_relevance_manifest": thread["legal_relevance_manifest"],
                "evidence_manifest": thread["evidence_manifest"],
            }

            prepared = await self.archive_service.prepare_document(
                filename=thread["thread_filename"],
                text=thread["text"],
                metadata=thread_metadata,
            )

            retention_mode = prepared["retention_mode"]
            retention_counts[retention_mode] = retention_counts.get(retention_mode, 0) + 1

            if not prepared.get("duplicate") and retention_mode == "exact_reference":
                success = await self.rag_service.add_text_document(
                    thread["text"],
                    source=thread_source,
                    metadata={
                        **thread_metadata,
                        "filename": thread["thread_filename"],
                        "retention_mode": retention_mode,
                        "content_hash": prepared.get("content_hash"),
                    },
                )
                if not success:
                    continue

            archive_result = await self.archive_service.process_document(
                file_path=thread_source,
                filename=thread["thread_filename"],
                text=thread["text"],
                metadata=thread_metadata,
                precomputed=prepared,
            )

            if archive_result.get("skipped_duplicate"):
                skipped_duplicates += 1
                continue

            await self.research_vault_service.append_entry(
                "archive_ingest",
                {
                    "source_kind": "chatgpt_export_thread",
                    "parent_filename": file.filename,
                    "thread_title": thread["title"],
                    "thread_filename": thread["thread_filename"],
                    "raw_text": thread["text"],
                    "analysis": archive_result,
                    "metadata": thread_metadata,
                    "timestamp": datetime.now().isoformat(),
                },
                source_ref=thread_source,
                file_hash=archive_result.get("file_hash"),
                content_hash=archive_result.get("content_hash"),
            )

            imported_threads += 1
            archive_document_count += 1 if archive_result.get("archive_document_created") else 0
            personality_memory_count += 1 if archive_result.get("personality_memory_created") else 0
            formative_moments_count += int(archive_result.get("formative_moments_created", 0))
            legal_sensitive_threads += 1 if archive_result.get("legal_sensitivity") else 0

        if imported_threads == 0 and skipped_duplicates == 0:
            raise RuntimeError("Failed to import any conversations from the ChatGPT export")

        return {
            "message": f"Imported {imported_threads} conversation threads from '{file.filename}'",
            "imported_threads": imported_threads,
            "skipped_duplicates": skipped_duplicates,
            "archive_document_created": archive_document_count > 0,
            "archive_documents_created": archive_document_count,
            "personality_memory_created": personality_memory_count > 0,
            "personality_memories_created": personality_memory_count,
            "legal_sensitivity": legal_sensitive_threads > 0,
            "legal_sensitive_threads": legal_sensitive_threads,
            "formative_moments_created": formative_moments_count,
            "archive_type": "chatgpt_export",
            "era_label": None,
            "retention_counts": retention_counts,
            "file_hash": upload_file_hash,
            "manual_direction": normalized_ingest_intent,
        }

    async def _handle_single_document(
        self,
        *,
        file,
        content: bytes,
        temp_file_path: str,
        upload_metadata: Dict,
        normalized_ingest_intent: str,
    ) -> Dict:
        extracted_text = await self.rag_service.extract_document_text(temp_file_path)
        prepared = await self.archive_service.prepare_document(
            filename=file.filename,
            text=extracted_text,
            metadata=upload_metadata,
            raw_bytes=content,
        )
        retention_mode = prepared["retention_mode"]

        success = True
        if not prepared.get("duplicate") and retention_mode == "exact_reference":
            success = await self.rag_service.add_document(
                temp_file_path,
                metadata={
                    **upload_metadata,
                    "retention_mode": retention_mode,
                    "content_hash": prepared.get("content_hash"),
                },
            )

        archive_result = (
            await self.archive_service.process_document(
                file_path=temp_file_path,
                filename=file.filename,
                text=extracted_text,
                metadata=upload_metadata,
                precomputed=prepared,
            )
            if success
            else {
                "archive_document_created": False,
                "personality_memory_created": False,
                "archive_type": "reference_document",
                "era_label": None,
                "legal_sensitivity": False,
                "formative_moments_created": 0,
                "retention_mode": retention_mode,
                "skipped_duplicate": False,
            }
        )

        if not (success or archive_result.get("skipped_duplicate")):
            raise RuntimeError("Failed to process document")

        if not archive_result.get("skipped_duplicate"):
            await self.research_vault_service.append_entry(
                "archive_ingest",
                {
                    "source_kind": "single_document",
                    "filename": file.filename,
                    "raw_text": extracted_text,
                    "analysis": archive_result,
                    "metadata": upload_metadata,
                    "timestamp": datetime.now().isoformat(),
                },
                source_ref=temp_file_path,
                file_hash=archive_result.get("file_hash"),
                content_hash=archive_result.get("content_hash"),
            )

        return {
            "message": f"Document '{file.filename}' processed successfully",
            "personality_memory_created": archive_result.get("personality_memory_created", False),
            "archive_document_created": archive_result.get("archive_document_created", False),
            "archive_type": archive_result.get("archive_type"),
            "era_label": archive_result.get("era_label"),
            "legal_sensitivity": archive_result.get("legal_sensitivity", False),
            "formative_moments_created": archive_result.get("formative_moments_created", 0),
            "retention_mode": archive_result.get("retention_mode"),
            "skipped_duplicate": archive_result.get("skipped_duplicate", False),
            "duplicate_of": archive_result.get("duplicate_of"),
            "file_hash": archive_result.get("file_hash"),
            "content_hash": archive_result.get("content_hash"),
            "manual_direction": normalized_ingest_intent,
        }
