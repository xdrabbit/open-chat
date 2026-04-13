#!/usr/bin/env python3

import argparse
import asyncio
import hashlib
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from config import config  # noqa: E402
from services.archive_service import ArchiveService  # noqa: E402
from services.chatgpt_export_parser import parse_chatgpt_export_file  # noqa: E402
from services.ollama_service import OllamaService  # noqa: E402
from services.openai_service import OpenAIService  # noqa: E402
from services.rag_service import create_rag_service  # noqa: E402
from services.research_vault_service import ResearchVaultService  # noqa: E402


def iter_files(base_dir: Path, extensions):
    for path in sorted(base_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in extensions:
            yield path


async def main():
    parser = argparse.ArgumentParser(description="Bulk import archive files into Open Chat memory pipelines.")
    parser.add_argument("directory", help="Directory containing archive files")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of files to import")
    args = parser.parse_args()

    base_dir = Path(args.directory).expanduser().resolve()
    if not base_dir.exists():
        raise SystemExit(f"Directory not found: {base_dir}")

    rag_service = create_rag_service()
    await rag_service.initialize()

    analysis_service = None
    if config.ARCHIVE_ANALYSIS_PROVIDER == "openai" and config.MODEL_PROVIDER == "openai":
        analysis_service = OpenAIService()
    elif config.ARCHIVE_ANALYSIS_PROVIDER == "local":
        analysis_service = OllamaService()

    archive_service = ArchiveService(rag_service.vector_store.db_path, analysis_service=analysis_service, rag_service=rag_service)
    await archive_service.initialize()
    research_vault_service = ResearchVaultService(rag_service.vector_store.db_path)
    await research_vault_service.initialize()

    supported_formats = set(rag_service.get_supported_formats())
    imported = 0

    for file_path in iter_files(base_dir, supported_formats):
        if args.limit and imported >= args.limit:
            break

        print(f"Importing {file_path}")
        metadata = {
            "filename": file_path.name,
            "source_directory": str(file_path.parent),
            "bulk_imported_at": __import__("datetime").datetime.now().isoformat(),
            "file_hash": hashlib.sha256(file_path.read_bytes()).hexdigest(),
        }

        if file_path.suffix.lower() == ".json":
            threads = parse_chatgpt_export_file(str(file_path))
            if not threads:
                print("  skipped: unsupported JSON structure")
                continue

            for thread in threads:
                if args.limit and imported >= args.limit:
                    break

                thread_source = f"{file_path}::{thread['thread_filename']}"
                thread_metadata = {
                    **metadata,
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

                prepared = await archive_service.prepare_document(
                    filename=thread["thread_filename"],
                    text=thread["text"],
                    metadata=thread_metadata,
                )

                if prepared.get("duplicate"):
                    duplicate = prepared["duplicate"]
                    print(f"  skipped duplicate: {thread['title']} -> {duplicate['filename']} ({duplicate['match_type']})")
                    continue

                retention_mode = prepared["retention_mode"]
                success = True
                if retention_mode == "exact_reference":
                    success = await rag_service.add_text_document(
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
                    print(f"  failed: {thread['title']}")
                    continue

                analysis = await archive_service.process_document(
                    file_path=thread_source,
                    filename=thread["thread_filename"],
                    text=thread["text"],
                    metadata=thread_metadata,
                    precomputed=prepared,
                )
                await research_vault_service.append_entry(
                    "archive_ingest",
                    {
                        "source_kind": "chatgpt_export_thread",
                        "parent_filename": file_path.name,
                        "thread_title": thread["title"],
                        "thread_filename": thread["thread_filename"],
                        "raw_text": thread["text"],
                        "analysis": analysis,
                        "metadata": thread_metadata,
                    },
                    source_ref=thread_source,
                    file_hash=analysis.get("file_hash"),
                    content_hash=analysis.get("content_hash"),
                )
                print(
                    f"  thread={thread['title']} "
                    f"archive_type={analysis.get('archive_type')} "
                    f"retention_mode={analysis.get('retention_mode')} "
                    f"era={analysis.get('era_label')} "
                    f"personality_memory_created={analysis.get('personality_memory_created')}"
                )
                imported += 1
            continue

        text = await rag_service.extract_document_text(str(file_path))
        prepared = await archive_service.prepare_document(
            filename=file_path.name,
            text=text,
            metadata=metadata,
            raw_bytes=file_path.read_bytes(),
        )
        if prepared.get("duplicate"):
            duplicate = prepared["duplicate"]
            print(f"  skipped duplicate -> {duplicate['filename']} ({duplicate['match_type']})")
            continue

        retention_mode = prepared["retention_mode"]
        success = True
        if retention_mode == "exact_reference":
            success = await rag_service.add_document(
                str(file_path),
                {**metadata, "retention_mode": retention_mode, "content_hash": prepared.get("content_hash")},
            )
        if not success:
            print("  failed: rag ingestion")
            continue

        analysis = await archive_service.process_document(
            file_path=str(file_path),
            filename=file_path.name,
            text=text,
            metadata=metadata,
            precomputed=prepared,
        )
        await research_vault_service.append_entry(
            "archive_ingest",
            {
                "source_kind": "single_document",
                "filename": file_path.name,
                "raw_text": text,
                "analysis": analysis,
                "metadata": metadata,
            },
            source_ref=str(file_path),
            file_hash=analysis.get("file_hash"),
            content_hash=analysis.get("content_hash"),
        )
        print(
            f"  archive_type={analysis.get('archive_type')} "
            f"retention_mode={analysis.get('retention_mode')} "
            f"era={analysis.get('era_label')} "
            f"personality_memory_created={analysis.get('personality_memory_created')}"
        )
        imported += 1

    stats = archive_service.get_stats()
    print("Done.")
    print(stats)


if __name__ == "__main__":
    asyncio.run(main())
