from config import config


class PolicyService:
    """Centralize mode and privacy decisions."""

    VALID_INGEST_INTENTS = {"auto", "personality", "reference"}

    def should_attach_private_context(self) -> bool:
        """False when remote OpenAI should only receive the user's live text input."""
        if (
            config.MODEL_PROVIDER == "openai"
            and config.CLOUD_TEXT_ONLY
            and not config.is_lan_safe_url(config.OPENAI_BASE_URL)
        ):
            return False
        return True

    def allow_remote_image_upload(self) -> bool:
        """False when remote OpenAI must not receive uploaded images."""
        return self.should_attach_private_context()

    def normalize_ingest_intent(self, ingest_intent: str) -> str:
        normalized = (ingest_intent or "auto").strip().lower()
        if normalized not in self.VALID_INGEST_INTENTS:
            raise ValueError("ingest_intent must be auto, personality, or reference")
        return normalized
