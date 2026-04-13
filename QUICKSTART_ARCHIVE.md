# Quick Start Archive Guide

This guide is for the current setup on Blackbird.

## Current Behavior

- Uploaded files are parsed locally.
- Archive analysis runs locally.
- ComfyUI image generation is local.
- OpenAI is used for live typed chat.
- `CLOUD_TEXT_ONLY=True`, so OpenAI chat does **not** receive local RAG or personality memory.

That means:

- archive building: local
- archive distillation: local
- legal/reference storage: local
- research vault: local and encrypted
- live chat text: cloud

## File Types

You can upload:

- `.txt`
- `.md`
- `.pdf`
- `.docx`
- `.json` for ChatGPT `conversations.json` exports

## Two Retention Modes

### `distill_only`

Used for archive/personality-style material.

What it means:

- raw file is processed locally
- personality/profile summaries are kept
- formative moments may be kept
- hashes are kept
- raw text is **not** retained for normal RAG retrieval

### `exact_reference`

Used for legal/reference-style material.

What it means:

- raw file is processed locally
- exact retrieval chunks are kept in local RAG
- hashes are kept
- this material does **not** shape personality

## Duplicate Protection

Each import computes:

- `file_hash`: hash of raw file bytes
- `content_hash`: hash of normalized text

If the same content is imported again, it is skipped as a duplicate.

## Single File Upload

Use the web UI:

1. Open `http://192.168.0.40:8000`
2. Drag in one file
3. Read the upload message

Typical outcomes:

- “distilled into background personality memory”
  This is archive-style material and was stored as `distill_only`.

- “quarantined to exact reference memory”
  This is legal/reference material and was stored as `exact_reference`.

- “skipped as a duplicate”
  The content was already imported before.

## ChatGPT Export JSON

If you upload a ChatGPT `conversations.json` file:

- the file is parsed locally
- each thread is split out locally
- each thread is classified separately
- legal-heavy threads go to `exact_reference`
- relational threads may become `distill_only`
- duplicates are skipped automatically

The upload response will tell you:

- how many threads were imported
- how many threads created personality memory
- how many stayed legal/reference only
- how many duplicates were skipped

## Bulk Import

For large imports, use the CLI instead of the browser.

Example:

```bash
./venv/bin/python bulk_import_archive.py /path/to/archive --limit 25
```

Recommended workflow:

1. Start with `--limit 25`
2. Review results
3. Increase to `50`, `100`, or more
4. Keep going in batches

The script will print, per file or thread:

- archive type
- retention mode
- era
- whether personality memory was created
- whether a duplicate was skipped

## Research Vault

There is an encrypted research vault.

What it does:

- stores sealed research entries
- can keep raw diagnostic/archive material for the research module
- has no normal cleartext read endpoint

What you can do:

- check stats: `GET /research-vault/stats`
- wipe it completely: `DELETE /research-vault`

What you cannot do through the app:

- browse entries
- read cleartext entries
- edit individual entries

## Current Privacy Boundary

Right now:

- local archive memory exists
- OpenAI chat does **not** use it

Why:

- `.env` has `CLOUD_TEXT_ONLY=True`

So if the model says it does not have access to your archive, that is currently expected.

To change that later, we would need to:

- set `CLOUD_TEXT_ONLY=False`, or
- use a local model for archive-aware chat

## Useful Checks

RAG stats:

```bash
curl -sS http://127.0.0.1:8000/rag/stats
```

Archive stats:

```bash
curl -sS http://127.0.0.1:8000/archive/stats
```

Conversation stats:

```bash
curl -sS http://127.0.0.1:8000/conversations/stats
```

Research vault stats:

```bash
curl -sS http://127.0.0.1:8000/research-vault/stats
```

## Good First Test

1. Upload one copied chat thread
2. Upload one `conversations.json`
3. Confirm the upload messages match expectations
4. Check `/archive/stats`
5. Check `/rag/stats`

## Important Reminder

The archive system is ready.

The current OpenAI chat path is intentionally privacy-limited.

So think of the system right now as:

- a working local archive and memory builder
- a separate live cloud chat interface

Those two can be joined later if you decide to change the privacy boundary.
