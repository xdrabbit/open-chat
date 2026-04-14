# Open Chat Refactor Plan

## Objective

Move from a high-value prototype to a controlled architecture without losing the working behaviors that matter:

- archive ingestion
- personality distillation
- legal/reference separation
- sealed research summaries
- local ComfyUI rendering
- explicit dream-to-draw flow

## Phase 0: Stabilize

This phase is about stopping entropy.

### Tasks

- keep the current feature set stable
- stop adding cross-cutting behavior inside `backend/main.py`
- treat current routes as integration shells only
- keep `.runtime/`, temp artifacts, generated media, and databases out of git
- document the operating modes

### Deliverables

- architecture doc
- refactor plan
- clear runtime scripts

## Phase 1: Extract Orchestrators

This is the first real code refactor.

### Extract first

- `chat_orchestrator.py`
- `draw_orchestrator.py`
- `ingest_orchestrator.py`
- `research_orchestrator.py`

### Why first

Right now route handlers are doing orchestration, policy, persistence, and tool calls together. That is the single largest maintainability problem.

### Result

`backend/main.py` should mostly become:

- input validation
- route binding
- response shaping

Not:

- memory assembly logic
- provider selection logic
- draw pipeline logic
- research pipeline logic

## Phase 2: Make Policy Explicit

Create a dedicated `policy_service.py`.

### Move into policy service

- `CLOUD_TEXT_ONLY` decisions
- legal sensitivity routing
- retention mode routing
- allowed provider per lane
- allowed consumer per artifact

### Result

Every route should ask policy questions through one interface instead of hardcoding them.

## Phase 3: Separate Memory Lanes

Define explicit repositories or services for each memory type.

### Extract

- `reference_memory_service.py`
- `personality_memory_service.py`
- `archive_memory_service.py`
- `research_memory_service.py`

### Keep RAG-specific concerns only in RAG

`rag_service.py` should become about:

- chunking
- embeddings
- vector search
- exact retrieval

It should not own:

- personality policy
- archive interpretation
- research sealing

## Phase 4: Normalize Artifact Metadata

Introduce a shared artifact model.

### Add a canonical artifact schema

Required fields:

- `artifact_id`
- `kind`
- `source_kind`
- `filename`
- `file_hash`
- `content_hash`
- `sensitivity`
- `retention_mode`
- `allowed_consumers`
- `provenance`
- `created_at`

### Why

The project already behaves as if this schema exists. It needs to exist explicitly.

## Phase 5: Separate Draw Pipeline

The draw path is valuable and should be treated as a first-class subsystem.

### Extract

- `image_prompt_service.py`
- `draw_orchestrator.py`
- `image_artifact_service.py`

### Responsibilities

- dream prompt expansion
- style normalization
- ComfyUI invocation
- provenance persistence
- generated image metadata

### Result

Chat no longer owns image generation logic. It only invokes the draw lane when asked.

## Phase 6: Research Isolation

The research vault should become more obviously separate.

### Extract

- `research_report_service.py`
- `research_ingest_service.py`

### Rules

- no raw vault read path in normal UI
- no archive transcript leakage in reports
- reports generated only from synthesized context
- research append path available from orchestrators, not from everywhere

## Phase 7: UI Mode Separation

The frontend should expose system modes directly.

### Add explicit mode affordances

- `Chat`
- `Draw`
- `Archive`
- `Research`
- `Admin`

### Why

The user should not need to remember hidden behavior conventions.

### Concrete examples

- `Draw` mode can show `/draw` guidance and prompt presets
- `Archive` mode can show retention choices and import summaries
- `Research` mode can show brief/full report controls and caveats

## First Code Splits To Do Next

These are the highest-value first extractions.

### 1. Chat orchestration

Move out of `backend/main.py`:

- private context attachment
- provider call selection
- AI-initiated image handling
- persistence side effects
- research-vault append logic

### 2. Draw orchestration

Move out of `backend/main.py`:

- dream prompt generation
- ComfyUI render invocation
- draw response shaping
- draw provenance storage

### 3. Archive ingest orchestration

Move out of upload route:

- parse type selection
- manual direction overrides
- retention routing
- personality fallback application
- archive result assembly

## What Not To Do

Avoid these until the first refactor is complete:

- adding more hidden chat commands beyond the current useful set
- adding more memory tables without an explicit lane
- mixing research summaries back into normal personality memory
- adding cloud image generation before draw orchestration is stable
- trying to replace SQLite prematurely

## Success Criteria

The refactor is working when:

- `backend/main.py` becomes small and legible
- each lane has one orchestrator
- policy decisions are centralized
- memory artifacts have explicit types and consumers
- draw requests are deliberate and predictable
- research remains sealed

## Recommended Next Task

Refactor `backend/main.py` by extracting:

1. `chat_orchestrator.py`
2. `draw_orchestrator.py`

That is the best first move because it reduces the most complexity without changing the data model yet.
