# Full Patterns — per-cluster evidence

**Provenance**: generated 2026-06-09 (#366) from the deduped 2026 failure
corpus (N=40, 2026-01-06 → 2026-06-07; telemetry shards + global
failures.jsonl, classified by map_freetext_root_causes.py).
Load on COMPLEX issues; patterns-critical.md is the always-on summary.

## VERIFICATION_GAP (11)

- **#78** (buddy): VERIFICATION_GAP
  - prevention: PLAN should specify data flow between sequential processing steps; MAP-PLAN acceptance criteria should include explicit verification of data handoff between met
- **#157** (mymoney-dev): Agent stated dependency resolved but didn't verify exact implementation details
- **#156** (mymoney-dev): Agent used outdated pattern without checking if spec was updated
- **#156** (mymoney-dev): Agent wrote defensive comment without checking database constraints
- **#157** (mymoney-dev): Agent added new field without checking ALL formulas that might need it
- **#157** (mymoney-dev): Agent didn't verify column dependencies and execution order
- **#160** (mymoney-dev): Agent didn't validate label semantics match data field semantics
- **#160** (mymoney-dev): Agent listed field in dependencies but didn't verify it's used in implementation
- **#160** (mymoney-dev): Agent assumed consecutive year data, filtered by modulo instead of deriving from actual rows
- **#160** (mymoney-dev): Agent assumed projectionMode is always numeric string when not 'current', didn't add validation
- **#160** (mymoney-dev): Agent documented expected data shapes but didn't add validation before processing

## AMBIGUITY_UNRESOLVED (3)

- **#156** (mymoney-dev): Agent identified contradiction but failed to resolve it definitively
- **#156** (mymoney-dev): Agent discussed both interpretations but didn't pick one definitively
- **#157** (mymoney-dev): Agent didn't call out naming inconsistency risk explicitly

## UNMAPPED (3)

- **#156** (mymoney-dev): Agent copied pattern verbatim without understanding which variables are needed
- **#157** (mymoney-dev): Agent copied acceptance criteria from issue description without aligning to implementation approach
- **#311** (): AC4 metric measured task-unattributed (unchanged by feature) instead of project-unattributed (the actual win);
  - prevention: before/after metrics must measure the dimension the feature changes; per-message precedence must prevent a one-off mined signal from overriding the physical cwd

## SCOPE_CREEP (2)

- **#156** (mymoney-dev): Agent planned tests for explicit spec cases but missed implicit filter validation
- **#160** (mymoney-dev): Agent only implemented primary warning scenario, didn't consider secondary deficit type

## DOCUMENTATION (2)

- **#160** (mymoney-dev): Agent wrote functionally correct logic but didn't document state handling priority explicitly
- **#157** (mymoney-dev): Agent didn't specify test precision requirements in plan

## LLM_OUTPUT_SCHEMA (1)

- **#learning-dashboard** (buddy): LLM_OUTPUT_SCHEMA
  - prevention: When consuming LLM-generated JSON, handle multiple plausible keys. Or constrain the output schema in the analysis prompt.

## SERVER_DEP_MANAGEMENT (1)

- **#431** (buddy): SERVER_DEP_MANAGEMENT
  - prevention: NEVER use 'uv sync' on the server. Always use 'uv pip install <package>' for adding new dependencies. Server dep management is pip-based, not lockfile-based.

## BLOCKING_FIRE_AND_FORGET (1)

- **#phase2-live-test** (buddy): BLOCKING_FIRE_AND_FORGET
  - prevention: Background tasks that don't affect the response should use asyncio.create_task(), not await. Review all callers of slow background operations.

## ASYNCPG_POOL_VS_CONNECTION (1)

- **#sprint4-audit-logger** (buddy): ASYNCPG_POOL_VS_CONNECTION
  - prevention: When writing DB code that requires transactions in this codebase, remember: get_pool() returns a Pool, not a Connection. Transactions require pool.acquire() fir

## PIPECAT_PIPELINE_DEADLOCK (1)

- **#sprint4-ui-state-query** (buddy): PIPECAT_PIPELINE_DEADLOCK
  - prevention: Never await a response from the same WebSocket pipeline that your handler is blocking. Pipecat's transport serializes frame processing — if a tool handler block

## MISSING_TEST (1)

- **#211** (mymoney-dev): MISSING_TEST
  - prevention: Read acceptance criteria literally - if tests required in phase, create tests in that phase

## LINT_ERROR (1)

- **#235** (mymoney-dev): LINT_ERROR
  - prevention: Run ruff check on all changed files before committing

## NO_ROOT_CAUSE (1)

- (mymoney-dev): 

## PATH_EXPANSION (1)

- **#learning-dashboard** (buddy): PATH_EXPANSION
  - prevention: Always use Path(...).expanduser() when path comes from config. PROVE should verify file exists at expected absolute path after write operations.

## SQL_RESERVED_WORD (1)

- **#phase2-live-test** (buddy): SQL_RESERVED_WORD
  - prevention: Always check column names against PostgreSQL reserved word list. Quote identifiers that match reserved words.

## WRONG_TABLE_NAME (1)

- **#phase2-live-test** (buddy): WRONG_TABLE_NAME
  - prevention: Always verify table names by reading init-db.sql or running \dt before writing queries. Never trust spec table names without verification.

## INVALID_SQL_CONSTRUCT (1)

- **#phase2-live-test** (buddy): INVALID_SQL_CONSTRUCT
  - prevention: Test complex SQL against actual PostgreSQL before shipping. DISTINCT + ORDER BY in aggregates is a known PostgreSQL limitation.

## OPENAI_STRICT_SCHEMA (1)

- **#phase2-live-test** (buddy): OPENAI_STRICT_SCHEMA
  - prevention: When building OpenAI JSON schemas with strict=True: every object needs additionalProperties: false and every property in required. Test schema with a real API c

## SEQUENTIAL_IO (1)

- **#phase2-live-test** (buddy): SEQUENTIAL_IO
  - prevention: When multiple async DB/IO calls are independent, always use asyncio.gather(). Review extraction pipeline for parallelization opportunities.

## MISSING_SERVICE_WIRING (1)

- **#sprint4-ui-state-query** (buddy): MISSING_SERVICE_WIRING
  - prevention: When a new capability needs a service, verify that service is actually in ServiceContainer before writing self.deps.get() calls. If not, check whether the servi

## WRONG_CONN_ID_SCOPE (1)

- **#sprint4-ui-state-query** (buddy): WRONG_CONN_ID_SCOPE
  - prevention: ContextVars set in the voice pipeline represent Pipecat transport connections, NOT browser UI connections. Never use voice pipeline conn_id to target web UI Web

## MISSING_INTERFACE_METHODS (1)

- **#sprint4-ui-state-query** (buddy): MISSING_INTERFACE_METHODS
  - prevention: When writing code that depends on duck-typed methods, read the actual target class and verify method signatures exist before writing the calling code. No interf

## MULTI_MODEL (1)

- **#211** (mymoney-dev): MULTI_MODEL
  - prevention: Always import relationship target classes at module level, not in TYPE_CHECKING blocks

## STUB_HANDLERS (1)

- **#582** (mymoney-dev): stub_handlers
