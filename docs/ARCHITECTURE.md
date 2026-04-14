# Open Chat Target Architecture

## Purpose

This system should not be treated as a single chat app with extra features. The correct shape is a multimodal memory system with hard boundaries between:

1. interaction
2. orchestration
3. memory
4. generation
5. policy

The current codebase is useful, but too much behavior is fused into `backend/main.py` and a handful of large services. That makes every new feature leak into every other feature.

## Current Problems

These are the main boundary violations in the current prototype:

- chat routing, memory retrieval, image generation, research logging, and persistence all meet in the same request handlers
- archive ingestion, distillation, RAG indexing, and legal/privacy policy are too tightly coupled
- image generation is split between keyword heuristics, chat behavior, UI behavior, and ComfyUI service logic
- the same SQLite store is carrying multiple concepts:
  - exact retrieval
  - personality background
  - archive analysis
  - sealed research data
- provider selection is global, but different lanes want different providers
- privacy policy is enforced partly by config, partly by route logic, and partly by behavior conventions

## Desired System Shape

### 1. Interaction Layer

This is the user-facing shell only.

Responsibilities:

- web chat UI
- image generation UI
- archive upload UI
- research report UI
- explicit mode controls

Non-responsibilities:

- no archive classification
- no retrieval assembly
- no legal/privacy decisions
- no generation heuristics

Suggested frontend modes:

- `Live Chat`
- `Archive Ingest`
- `Draw`
- `Research`
- `Admin`

### 2. Orchestration Layer

This should be the main application brain, but not the main implementation body.

Responsibilities:

- route requests to the correct lane
- apply policy decisions
- assemble context deliberately
- track provenance
- persist event metadata

Example orchestration decisions:

- should this chat attach private context?
- should this upload become `distill_only` or `exact_reference`?
- should this request go to OpenAI, Ollama, or ComfyUI?
- should this artifact be visible to the user, only to research, or both?

Suggested modules:

- `chat_orchestrator.py`
- `ingest_orchestrator.py`
- `draw_orchestrator.py`
- `research_orchestrator.py`
- `policy_service.py`

### 3. Memory Layer

This is the real core of the project.

Memory must be lane-based, not blob-based.

#### A. Exact Reference Memory

Use for:

- legal material
- precise instructions
- names, dates, clauses, addresses
- documents requiring fidelity

Properties:

- source-linked
- retrievable
- citation-capable
- never allowed to silently shape personality

#### B. Personality Memory

Use for:

- tone
- continuity
- relational geography
- stylistic preferences
- stable interaction patterns

Properties:

- distilled
- non-verbatim
- background-only
- not factual authority

#### C. Archive Analysis Memory

Use for:

- era summaries
- turning points
- model-evolution observations
- human-state summaries
- formative moments

Properties:

- analytic
- synthesis-heavy
- may inform research and long-term continuity
- should not be confused with exact retrieval

#### D. Research Vault

Use for:

- sealed longitudinal analysis
- diagnostic pattern storage
- black-box summaries inaccessible through normal user flows

Properties:

- encrypted
- append-only within the app boundary
- not surfaced as raw text
- deleteable as a whole

### 4. Generation Layer

Generation tools should be treated as capabilities, not personalities.

#### Chat Models

- OpenAI for live cloud reasoning
- Ollama for private/local reasoning

#### Image Generation

- ComfyUI for local rendering
- optional OpenAI image lane if explicitly enabled later

#### Voice

- local or remote TTS/STT as separate capabilities

Key rule:

- generation systems should not directly decide memory policy

### 5. Policy Layer

This should become an explicit subsystem.

Responsibilities:

- cloud vs local boundaries
- lane access control
- legal sensitivity handling
- retention mode decisions
- research vault visibility rules

Every artifact should carry:

- `artifact_id`
- `artifact_type`
- `source_path`
- `retention_mode`
- `sensitivity`
- `allowed_consumers`
- `provenance`
- `created_at`
- `content_hash`
- `file_hash`

## Recommended Runtime Lanes

### Live Chat Lane

Input:

- user message

Pipeline:

- choose provider
- attach only allowed context
- generate response
- optional TTS
- persist event

### Archive Ingest Lane

Input:

- file or export

Pipeline:

- parse
- classify
- retention decision
- exact indexing and/or distillation
- archive analysis
- research vault append

### Draw Lane

Input:

- visual prompt

Pipeline:

- dream prompt expansion
- ComfyUI render
- persist provenance
- return image

### Research Lane

Input:

- research brief/full request

Pipeline:

- read sealed aggregates only
- synthesize non-verbatim report
- return structured report

## Recommended Storage Model

The project currently uses a single RAG SQLite file for several concepts. That is acceptable for a prototype, but the concepts must still be separated logically.

Preferred logical stores:

- `conversation_store`
- `reference_store`
- `personality_store`
- `archive_store`
- `research_store`
- `artifact_store`

These may still live in SQLite at first, but should not share vague table semantics.

## What Good Looks Like

The system is in good shape when:

- chat behavior changes do not require archive ingestion edits
- draw behavior changes do not require RAG changes
- legal/reference material cannot silently become personality memory
- research output cannot leak raw archive text
- the user can tell which mode they are in
- the system can explain why a given memory artifact was used

## Immediate Principles

Until a deeper refactor is complete, new work should follow these rules:

1. no new mixed-responsibility routes
2. no new hidden policy decisions in UI code
3. no new memory type without an explicit lane definition
4. no new provider behavior without provenance logging
5. no new archive feature unless it states whether it affects:
   - exact reference
   - personality
   - research
   - all three
