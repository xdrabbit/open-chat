from typing import Any, Dict, Optional


class PersonalityMemoryService:
    """Own distilled personality-memory storage and prompt assembly."""

    def __init__(self, vector_store, enabled_getter):
        self.vector_store = vector_store
        self.enabled_getter = enabled_getter

    def is_enabled(self) -> bool:
        return bool(self.enabled_getter())

    async def save_memory(self, source: str, filename: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        if not self.is_enabled() or not content.strip():
            return False
        return await self.vector_store.save_persona_memory(source, filename, content.strip(), metadata)

    async def delete_memories(
        self,
        *,
        source: Optional[str] = None,
        filename: Optional[str] = None,
        content_hash: Optional[str] = None,
    ) -> int:
        return await self.vector_store.delete_persona_memories(
            source=source,
            filename=filename,
            content_hash=content_hash,
        )

    async def get_context(self, limit: int = 2) -> str:
        if not self.is_enabled():
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
