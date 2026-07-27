---
name: DocuSense phased build
overview: "Phased implementation plan for DocuSense: a Next.js 15 + FastAPI + pgvector multi-document RAG app with two-stage retrieval, cross-document reasoning, document comparison, and a retrieval evaluation dashboard."
todos:
  - id: phase-0
    content: "Phase 0: repo layout, Docker Compose pgvector, Alembic initial migration, FastAPI + Next.js skeletons"
    status: pending
  - id: phase-1
    content: "Phase 1: NextAuth JWT bridge, user upsert, workspace CRUD, UI shell"
    status: pending
  - id: phase-2
    content: "Phase 2: upload, PyMuPDF extract, fixed chunker, batch embed, status machine"
    status: pending
  - id: phase-3
    content: "Phase 3: stage-1 retrieval, generation with citations, SSE chat, retrieval logging"
    status: pending
  - id: phase-4
    content: "Phase 4: cross-encoder re-ranking, toggleable, stage-2 logging"
    status: pending
  - id: phase-5
    content: "Phase 5: workspace-wide retrieval and cross-document synthesis"
    status: pending
  - id: phase-6
    content: "Phase 6: semantic chunker, dual-strategy chunk sets, strategy-scoped retrieval"
    status: pending
  - id: phase-7
    content: "Phase 7: chunk ratings, precision@k + MRR, A/B replay, eval dashboard"
    status: pending
  - id: phase-8
    content: "Phase 8: section-aligned document comparison with cited structured diff"
    status: pending
  - id: phase-9
    content: "Phase 9: conversation memory + follow-up query rewriting"
    status: pending
  - id: phase-10
    content: "Phase 10: error/empty states, retries, rate limiting, deploy notes"
    status: pending
isProject: false
---

# DocuSense — Phased Implementation Plan

## 1. Critique of the Brief

The brief is unusually well-specified. Points worth flagging:

- **Eval framework arrives too late (Phase 7).** `retrieval_logs` must be written from the *first* query onward or you'll have no baseline data for the "re-ranking improved MRR from X to Y" claim. I've moved logging (write-only, no UI) into Phase 3 and kept the dashboard in Phase 7. This is the only sequencing change I'm making.
- **A/B comparison of chunking strategies has a hidden cost:** comparing fixed vs semantic on "the same query set" requires each document to be chunked and embedded *twice* (once per strategy), with retrieval filtered by strategy. This roughly doubles embedding cost and storage. The schema supports it from Phase 2 (`chunking_strategy` column), but re-chunking existing docs with the semantic strategy is an explicit step in Phase 6. Alternative (per-document strategy choice) makes A/B unsound — same query hitting different chunk sets isn't controlled. Dual-chunking is correct; flagging the cost.
- **Precision@k needs a definition to be honest.** With user ratings as ground truth, unrated chunks are ambiguous. Plan: precision@k computed only over queries where all top-k chunks are rated; MRR uses rank of first chunk rated relevant. The dashboard will show coverage (% of queries fully rated) so the metrics aren't misleading.
- **Streaming + citations tension:** citations are only final after generation completes. Plan: SSE stream with `token` events during generation, then a final `citations` event. Frontend renders text progressively, attaches citations at the end.
- **Risk: pgvector filtered search.** Stage-1 retrieval always filters by `workspace_id` (and sometimes `document_id`, `chunking_strategy`). HNSW with post-filtering can return fewer than K rows for small workspaces. Mitigation: use pgvector ≥0.8 (iterative index scans) and set `hnsw.ef_search` generously; workspaces here are small enough that this is a non-issue in practice, but the retrieval function will assert it got K candidates or fall back to exact scan.
- **`gpt-4.1` + `text-embedding-3-small`** are config constants as requested; if either name is unavailable on your account we swap the constant, nothing else.
- **Conversation memory late (Phase 9) is correct** — but the `conversations`/`messages` tables exist from Phase 0 and chat writes to them from Phase 3, so Phase 9 is purely "use history in the prompt," not a migration.

## 2. Architecture Decisions (settled)

- **Auth bridge:** NextAuth (JWT strategy, Google + GitHub). FastAPI verifies the token (shared `NEXTAUTH_SECRET`, HS256 via `python-jose`) and upserts `users` on first authenticated request. No Auth.js DB adapter, no ORM in Next.js. Frontend calls FastAPI directly with `Authorization: Bearer`.
- **Async processing:** FastAPI `BackgroundTasks`; `documents.status` state machine: `uploaded → extracting → chunking → embedding → ready | failed` (+ `error_message`). UI polls status via TanStack Query.
- **Migrations:** Alembic + SQLAlchemy Core (async engine, `asyncpg`). Pipeline code stays framework-free; SQLAlchemy is used only as the DB access layer, not an abstraction over RAG logic.
- **Vector index: HNSW** (`vector_cosine_ops`, `m=16`, `ef_construction=64`). Justification: HNSW gives better recall/latency than IVFFlat at this scale, needs no training step (IVFFlat lists must be rebuilt as data grows from zero — awkward for an app that starts empty), and handles incremental inserts well. Build time/memory cost is irrelevant at MVP scale.
- **Document comparison: section alignment + targeted LLM comparison** (not full-doc). Full-doc prompting breaks on long PDFs (context limits), loses page-level citations, and produces ungrounded output. Instead: extract section outlines (from the semantic chunker's heading detection), align sections by title similarity + embedding similarity of section text, then run one LLM call per aligned pair (plus "missing in A/B" lists computed structurally). Output is structured (`ComparisonResult` Pydantic model) with per-finding citations. Cheaper, grounded, and cites pages.
- **Repo layout:** two-folder monorepo — `frontend/` (Next.js) and `backend/` (FastAPI), `docker-compose.yml` at root for Postgres+pgvector (`pgvector/pgvector:pg17` image).

## 3. Finalized Data Model

All PKs are UUIDs; all tables get `created_at`/`updated_at`.

- **users** — `id`, `email` (unique), `name`, `image`, `provider`. Upserted by FastAPI from verified JWT claims.
- **workspaces** — `id`, `user_id` FK, `name`. All queries scoped by ownership check.
- **documents** — `id`, `workspace_id` FK, `filename`, `storage_path`, `page_count`, `size_bytes`, `status` (enum above), `error_message`, `chunking_strategies` (text[] — which strategies have been run).
- **chunks** — `id`, `document_id` FK, `chunk_index`, `text`, `token_count`, `page_number`, `char_start`, `char_end`, `section_title` (nullable), `chunking_strategy` (enum `fixed|semantic`), `embedding vector(1536)`. Indexes: HNSW on `embedding`; btree on `(document_id, chunking_strategy)`.
- **conversations** — `id`, `workspace_id` FK, `title`.
- **messages** — `id`, `conversation_id` FK, `role` (`user|assistant`), `content`, `citations` (jsonb), `retrieval_log_id` FK nullable.
- **retrieval_logs** — `id`, `workspace_id` FK, `conversation_id` nullable, `query`, `chunking_strategy`, `rerank_enabled` (bool), `stage1_chunk_ids` (uuid[] in retrieved order), `stage2_chunk_ids` (uuid[] in re-ranked order, null if rerank off), `final_chunk_ids` (uuid[] actually sent to generator), `answer`, `abstained` (bool), `latency_ms_stage1` / `latency_ms_stage2` / `latency_ms_generate`, `model`.
- **chunk_ratings** — `id`, `retrieval_log_id` FK, `chunk_id` FK, `rating` (smallint: 1 relevant / 0 not relevant), unique on `(retrieval_log_id, chunk_id)`. Separate table (not jsonb on logs) so metrics are a SQL query.

## 4. Config Constants

Single `backend/app/config.py` (Pydantic Settings): `EMBEDDING_MODEL="text-embedding-3-small"`, `GENERATION_MODEL="gpt-4.1"`, `CROSS_ENCODER_MODEL="cross-encoder/ms-marco-MiniLM-L-6-v2"`, `CHUNK_SIZE_TOKENS=512`, `CHUNK_OVERLAP_TOKENS=64`, `SEMANTIC_MAX_TOKENS=512`, `RETRIEVE_K=20`, `RERANK_N=5`, `EMBED_BATCH_SIZE=64`, `MAX_UPLOAD_MB=50`.

## 5. Phases

### Phase 0 — Repo + infra
- Build: `frontend/` (create-next-app, TS strict, Tailwind, shadcn/ui init), `backend/` (FastAPI skeleton, `config.py`, `/healthz`), root `docker-compose.yml` (pgvector image), Alembic init + migration 001 creating **all** tables above + extensions, `.env.example` for both apps, README run instructions.
- Files: `docker-compose.yml`, `backend/app/{main,config,db}.py`, `backend/alembic/versions/001_initial.py`, `frontend/` scaffold.
- Accept: `docker compose up -d` + `alembic upgrade head` succeeds; `\d chunks` shows `vector(1536)` + HNSW index; `curl :8000/healthz` OK; `next dev` renders.

### Phase 1 — Auth + workspaces + shell
- Build: NextAuth (Google/GitHub, JWT strategy); FastAPI JWT dependency (`get_current_user`, upserts user); workspace CRUD endpoints + Pydantic models; typed API client (`frontend/lib/api.ts`, hand-written fetch wrapper with per-endpoint types); UI shell — sign-in page, workspace list/create, workspace layout with sidebar.
- Files: `frontend/app/api/auth/[...nextauth]/route.ts`, `frontend/lib/{api,auth}.ts`, `backend/app/{auth.py,routers/workspaces.py,schemas/workspace.py}`.
- Accept: sign in with Google; create/rename/delete workspace; a second account cannot see or fetch the first account's workspace (403).

### Phase 2 — Upload → extract → chunk (fixed) → embed → store
- Build: storage interface (`Storage` protocol: `save/open/delete`; `LocalStorage` impl); upload endpoint (PDF only, size cap) → BackgroundTask pipeline: `extract.py` (PyMuPDF, per-page text + char offsets), `chunking.py` (`Chunker` protocol; `FixedChunker` with tiktoken size/overlap, page attribution via char offsets), `embed.py` (batched OpenAI, retry w/ backoff), bulk insert chunks; status state machine + error capture; UI: dropzone upload, document list with live status polling, delete document (cascades chunks + file).
- Files: `backend/app/{storage.py,pipeline/{extract,chunking,embed,process}.py,routers/documents.py,schemas/document.py}`, `frontend/app/(workspace)/[id]/documents/*`.
- Accept: upload a 20-page PDF → status walks to `ready`; `SELECT count(*), min(page_number), max(page_number) FROM chunks WHERE document_id=…` sane; a corrupt PDF → `failed` + visible error; pytest unit tests for chunker (overlap, boundaries, page mapping).

### Phase 3 — Single-doc Q&A + citations + logging
- Build: `retrieve.py` (stage-1 pgvector cosine top-K, filters: workspace, optional document, strategy); `generate.py` (strict answer-from-context prompt, numbered context blocks `[1] (doc, p.X)`, abstain instruction, citation markers parsed from output); chat endpoint — SSE stream (`token` events, final `done` event w/ structured citations + `retrieval_log_id`); writes `retrieval_logs` + `messages` every query; UI: chat panel scoped to one document, streamed answer, citation chips → source panel showing chunk text + page.
- Files: `backend/app/{pipeline/{retrieve,rerank_stub…no—retrieve,generate}.py,routers/chat.py,schemas/chat.py}`, `frontend/app/(workspace)/[id]/chat/*`.
- Accept: answerable question returns correct answer with clickable citation showing right page/text; unanswerable question ("what's the capital of France" vs a lease PDF) → abstains; `retrieval_logs` row written with stage-1 ids + latency.

### Phase 4 — Cross-encoder re-ranking, toggleable
- Build: `rerank.py` (`CrossEncoderReranker`, lazy-loaded singleton model, scores K pairs → top-N); retrieval pipeline composed as explicit steps so stage-2 is a boolean flag on the chat request; `rerank_enabled` + `stage2_chunk_ids` + stage latencies logged; UI toggle in chat ("Re-ranking on/off").
- Files: `backend/app/pipeline/rerank.py`, edits to `chat.py`/`retrieve` composition, small UI toggle.
- Accept: same query with toggle on/off yields different `final_chunk_ids` in logs; both orderings logged; rerank latency recorded; first request warm-loads the model without blocking startup.

### Phase 5 — Cross-document retrieval + synthesis
- Build: chat scope = whole workspace (document filter becomes optional "focus" selector); context blocks always carry document name so the generator attributes per-source; prompt updated for multi-source synthesis ("Which proposal satisfies the policy?" style); citations grouped by document in UI.
- Files: edits to `retrieve.py` (already workspace-filtered — mostly prompt + API + UI changes), `frontend` chat scope selector.
- Accept: with 3 docs uploaded, a question whose answer spans 2 docs returns an answer citing both, with correct doc names and pages.

### Phase 6 — Semantic chunking + dual-strategy
- Build: `SemanticChunker` — split on PyMuPDF block/heading structure (font-size heuristics for headings) → paragraphs, greedy-pack under `SEMANTIC_MAX_TOKENS`, record `section_title`; "re-process with semantic" action per document (adds second chunk set, doesn't touch fixed chunks); retrieval takes a `chunking_strategy` parameter (default fixed) and it's logged; UI: per-query strategy picker.
- Accept: document has two chunk sets; semantic chunks carry section titles; same query under each strategy produces distinct logged retrievals; unit tests for heading detection + max-token cap.

### Phase 7 — Eval dashboard
- Build: rating UI on each answer's retrieved-chunk list (relevant / not relevant per chunk → `chunk_ratings`); metrics endpoint computing per-configuration (strategy × rerank) precision@k (k ∈ {1,3,5}) and MRR over fully-rated queries, plus rating coverage; "replay query set" action — re-run logged queries under a chosen configuration to get controlled A/B on identical queries; dashboard page: metric cards, config-comparison bar charts (recharts), query log table drill-down showing stage-1 vs stage-2 orderings side by side.
- Files: `backend/app/routers/eval.py`, `backend/app/eval/metrics.py`, `frontend/app/(workspace)/[id]/eval/*`.
- Accept: rate 10 queries; dashboard shows precision@5 and MRR per config; replaying the set with rerank on vs off produces a defensible "MRR X → Y" comparison; metrics match a hand-computed spot check.

### Phase 8 — Document comparison
- Build: `compare.py` — section outlines from semantic chunks; alignment by title fuzzy-match + section-embedding cosine; per-aligned-pair LLM diff call (differences / changed clauses, with page cites); unmatched sections → "only in A" / "only in B"; `ComparisonResult` Pydantic model; UI: pick two docs → side-by-side structured diff with citations.
- Accept: compare v1 vs v2 of a contract (one clause edited, one section removed) → diff flags the changed clause with both page numbers and lists the removed section; identical docs → "no material differences."

### Phase 9 — Conversation memory
- Build: conversation selection/creation in chat UI; last-M messages included in generation prompt; standalone-question rewrite step (small LLM call condensing follow-up + history into a self-contained retrieval query — logged query is the rewritten one, flagged as such); conversation list + titles.
- Accept: "What does the lease say about pets?" then "What's the penalty for violating it?" retrieves penalty-related chunks (pronoun resolved) and answers correctly.

### Phase 10 — Polish + deploy notes
- Build: empty states (no workspaces/docs/messages), upload validation errors, OpenAI failure handling (retry + surfaced errors), failed-doc retry button, loading skeletons, rate limiting on chat, `DEPLOY.md` (Vercel + Fly.io/Railway + managed Postgres w/ pgvector; storage interface → S3 note), final README.
- Accept: kill OpenAI key → chat shows a clean error, app doesn't crash; failed document retryable; fresh-clone-to-running in under 10 minutes following README.

## 6. Remaining Decisions Before Phase 0

1. **Rating scale:** binary relevant/not-relevant per chunk (recommended — makes precision@k/MRR unambiguous) vs graded 0–2. Plan assumes binary.
2. **Query replay cost:** Phase 7's A/B replay re-calls embeddings + optionally generation per query. OK to re-run generation too (better demo), or retrieval-only replay to save tokens? Plan assumes retrieval-only replay by default with a "with generation" option.
3. **Repo hygiene:** `copilot.md` at repo root looks like personal agent instructions — leave it, or should it be gitignored/moved? Plan leaves it untouched.

Defaults will be used for all three unless you say otherwise — none block Phase 0.