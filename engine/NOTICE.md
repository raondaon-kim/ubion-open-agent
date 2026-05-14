# Third-Party Attribution — engine/

This directory contains code adapted from the following projects.

---

## Hermes Agent

- **Source**: https://github.com/NousResearch/hermes-agent
- **License**: MIT
- **Copyright**: Copyright (c) 2025 Nous Research
- **Reference commit**: `b06e9993021a8eebd891fc60d52372446315b2f0` (2026-05-12)

License policy is defined in [`/research/hermes-license-policy.md`](../research/hermes-license-policy.md). Each adapted file carries its own header citing the upstream path and listing modifications.

### Files adapted from Hermes (Phase 1)

| Our path | Strength | Upstream path |
|----------|---------|--------------|
| `engine/storage/agent_home.py` | Port | `hermes_constants.py` (selected functions) |
| `engine/skills/usage.py` | Vendor copy | `tools/skill_usage.py` |
| `engine/skills/utils.py` | Vendor copy | `agent/skill_utils.py` |
| `engine/skills/preprocessing.py` | Vendor copy | `agent/skill_preprocessing.py` |
| `engine/learning/curator.py` | Vendor copy | `agent/curator.py` |
| `engine/core/errors.py` | Vendor copy | `agent/error_classifier.py` |
| `engine/core/retry.py` | Vendor copy | `agent/retry_utils.py` |
| `engine/core/budget.py` | Port | `run_agent.py` (class `IterationBudget`, lines 283-325) |
| `engine/core/agent.py` | Port | `run_agent.py` (`AIAgent` core, narrowed surface) |
| `engine/core/turn_setup.py` | Port | `run_agent.py:11707-12100` (pre-turn setup subset for Unit 3-1) |
| `engine/core/tool_dispatch.py` | Port | `run_agent.py:10453, 10495, 11019` (`_execute_tool_calls` / `_invoke_tool` / `_execute_tool_calls_sequential`). Strength downgraded from Vendor copy to Port — upstream is OpenAI-style ToolCalls + guardrail/checkpoint/activity_callback wiring incompatible with our Anthropic dataclass surface. Semantics preserved: cooperative interrupt skip, JSON-arg safety, error block shape. |
| `engine/storage/trajectory.py` | Vendor copy | `agent/trajectory.py` (44 lines, 0-line modification) |
| `engine/learning/context_engine.py` | Vendor copy | `agent/context_engine.py` (207 lines, 0-line modification) |
| `engine/learning/context_compressor.py` | Vendor copy | `agent/context_compressor.py` (1358 lines; only 4 import lines rewritten to point at our `engine.*` equivalents — body byte-identical) |
| `engine/learning/redact.py` | Vendor copy | `agent/redact.py` (341 lines, 0-line modification) |
| `engine/learning/model_metadata.py` | Port | `agent/model_metadata.py` — 3 symbols + 2 transitive helpers ported with Anthropic-only static catalog. Upstream is 1,574 lines covering 9-step multi-provider resolution; we replace it with `_CLAUDE_CONTEXT_LENGTHS` + `_DEFAULT_CONTEXT_LENGTH`. Token estimator is byte-identical to upstream. |
| `engine/learning/memory_provider.py` | Vendor copy | `agent/memory_provider.py` (218 lines, 0-line modification) |
| `engine/learning/memory_manager.py` | Vendor copy | `agent/memory_manager.py` (475 lines; only 2 import lines rewritten: memory_provider + tools.registry → engine.* equivalents — body byte-identical) |
| `engine/tools/registry.py` | Vendor copy (selective) | `tools/registry.py` — `tool_error` (L537-548) + `tool_result` (L551-563) only. Full registry adoption deferred to Unit 8. |
| `engine/skills/commands.py` | Vendor copy | `agent/skill_commands.py` (421 lines; only 2 import lines rewritten: `hermes_constants` + `agent.skill_preprocessing` → engine.* equivalents). |
| `engine/storage/agent_home.py` | Port (extended in Units 7, 4, 9.5) | Added `display_hermes_home()` (Unit 7), `is_wsl()` (Unit 4), and `get_workspace()` (post-Unit 9 workspace concept). UBION_AGENT_HOME = agent's persistent brain; UBION_WORKSPACE = the user's current target directory (poems, codebase, etc.) — distinct env vars, distinct semantics. |
| `engine/storage/atomic.py` | Port | `utils.py` (NousResearch/hermes-agent) — 4 atomic write helpers (`atomic_replace`, `atomic_json_write`, `_preserve_file_mode`, `_restore_file_mode`) + `is_truthy_value` ported from a 600-line upstream module that mixes YAML writes, retry helpers, and proxy detection irrelevant to our Phase 1 surface. |
| `engine/skills/manager.py` | Vendor copy | `tools/skill_manager_tool.py` (788 lines; 7 import lines rewritten — 4 top-level + 3 lazy — to engine.* equivalents). The vendored `registry.register(...)` call at module bottom runs against our stub registry in `engine/tools/registry.py`. |
| `engine/skills/_cfg_stub.py` | Independently authored | Phase 1 stub for `hermes_cli.config.cfg_get` (always returns default). |
| `engine/tools/path_security.py` | Vendor copy | `tools/path_security.py` (32 lines, 0-line modification) |
| `engine/tools/file_ops.py` | Independently authored | Phase 1 minimal file ops (`read_file` / `write_file` / `list_files`) — writes confined to the agent home via `path_security.validate_within_dir`. Hermes' full `file_tools.py` + `file_operations.py` are 2,600+ lines deferred to Phase 2. |
| `engine/tools/registry.py` (extended) | Independently authored (Unit 8) | Added `_ToolRegistry` stub so vendored modules can call `registry.register(...)` at module load without bringing in Hermes' full dispatcher. |
| `engine/storage/session_db.py` | Vendor copy | `hermes_state.py` (2689 lines; only 2 import lines rewritten — `agent.memory_manager` + `hermes_constants` → engine.* equivalents). SQLite + FTS5 (incl. CJK trigram) session storage. |
| `engine/tools/session_search.py` | Vendor copy | `tools/session_search_tool.py` (543 lines; 6 import lines rewritten — 2 top-level + 4 lazy — to engine.* equivalents). LLM-reranked full-text session search. |
| `engine/llm/aux_client.py` (extended in Unit 9) | Independently authored | Added `async_call_llm` (asyncio.to_thread wrapper around `call_llm`), `_run_async` helper (sync→async bridge for tool handlers, ~10 lines vs upstream 100), and `extract_content_or_reasoning` (vendored from auxiliary_client.py:4404 — strips inline think blocks + reasoning fallback). |
| `engine/server/api.py` | Independently authored (Unit 10, Reference strength) | OpenAI-compatible HTTP server: `/v1/chat/completions` (stream + non-stream), `/v1/models`, `/health`, Bearer auth. FastAPI + uvicorn; framework choice deviates from split-plan's aiohttp suggestion (see run-agent-split-plan.md note). |
| `engine/server/__main__.py` | Independently authored (Unit 10) | CLI launcher — `python -m engine.server` runs uvicorn against the FastAPI app. Reads UBION_HOST/UBION_PORT/UBION_API_TOKEN env vars. |
| `engine/llm/deepseek.py` | Independently authored (Unit 13) | DeepSeek API client. Reuses the official `openai` SDK pointed at `https://api.deepseek.com`. Translates Anthropic-shape messages/tools to OpenAI shape on send, normalises the OpenAI response back to our `ChatResponse` dataclass on receive. |
| `engine/llm/router.py` | Independently authored (Unit 13) | Provider router. Maps model name (or explicit provider override) → concrete LLM client (`AnthropicClient` or `DeepSeekClient`). Phase 1 Anthropic-only policy is now retired. |
| `engine/learning/model_metadata.py` (extended Unit 13) | Port | Added `_DEEPSEEK_CONTEXT_LENGTHS` catalog (deepseek-v4-flash / -v4-pro 128K + legacy deepseek-chat / -reasoner). `get_model_context_length` does Claude lookup first then DeepSeek. |
| `engine/server/api.py` (extended Unit 12 / 2026-05-13) | Independently authored | Added CORS middleware (`allow_origins=*` — Phase 1 (B) mobile access) + `/v1/models` lists `deepseek-v4-flash`, `deepseek-v4-pro`. Internal port moved from 8000 → 9000 (loopback only); user-facing entry is Vite dev 8803 with proxy. |
| `web/` (Unit 12, 2026-05-13) | Independently authored | Phase 1 (B) front-end. React 19 + TypeScript 6 + Vite 8 + Tailwind 4 + Noto Sans KR. Open WebUI 의 시각 언어 (다크/라이트 토글, 좌측 사이드바, 빈 상태 + suggested 카드, 입력 박스) 를 한국어 UI + 모바일 반응형 으로 재구성. SSE streaming 으로 단위 10 `/v1/chat/completions` 연결. 진입점은 `http://localhost:8803/` 하나로 통합 (모바일은 `http://<PC LAN IP>:8803/`). |
| `engine/core/prompt_caching.py` | Vendor copy | `agent/prompt_caching.py` (59 lines, 0-line modification) |
| `engine/core/prompt_builder.py` | Vendor copy | `agent/prompt_builder.py` (1298 lines; only 3 top-level import lines rewritten — hermes_constants/agent.skill_utils/utils → engine.* equivalents. Six lazy imports inside function bodies (tools.terminal_tool / tools.environments / gateway.session_context / hermes_cli.nous_subscription / tools.tool_backend_helpers / hermes_cli.config) are left untouched — each call site is already guarded by try/except so ImportError degrades gracefully when the corresponding module is absent in Phase 1. |
| `skills-bundle/` (2026-05-14, relocated from `engine/bundled_skills/` on the same day) | Vendor copy | `skills/` (86 SKILL.md folders across 22 categories; `index-cache/`, `dogfood/`, `inference-sh/` removed as Hermes-operator-specific). Read-only source seeded into `agent_home/skills/` on first boot via `ensure_bundled_skills_seeded()`. **Relocated out of the engine package (v0.4 structure-3 decision)** — Phase 3 tray apps download the bundle from the coordinator's `/v1/ubion/skills/bundle` endpoint (tar.gz, ~2 MB compressed, ETag-cached) into `~/.ubion-agent/.skill-cache/skills-bundle/`. Phase 1 dev environment falls back to `<repo>/skills-bundle/` directly. User edits to seeded skills are preserved across restarts. |
| `engine/server/api.py` (2026-05-14 extension) | Independently authored | Added `/v1/ubion/skills/bundle/info` (version + count metadata) and `/v1/ubion/skills/bundle` (tar.gz stream with ETag 304 short-circuit). Phase 1: served by the engine FastAPI itself. Phase 3: same contract moves to the central coordinator. |
| `engine.storage.agent_home.download_skills_bundle()` (2026-05-14) | Independently authored | Client helper for the Phase 3 tray app — fetches the bundle endpoint with `If-None-Match`, extracts the tar.gz atomically into `.skill-cache/skills-bundle/.partial/` then swaps into place, writes `.etag` for the next call. Pure stdlib (`urllib`, `tarfile`) — no extra deps. |
| `engine/skills/index.py` (2026-05-14) | Independently authored | Persistent skill frontmatter cache at `<agent_home>/.skill-index.json`. Re-parses only files whose mtime+size changed. 488 ms (cold) → 67 ms (warm) for 85 skills — supports §2.8 "boot → chat-ready 3 s" target. |
| `engine.llm.anthropic` (2026-05-14 lazy refactor) | Independently authored | Top-level `import anthropic` removed; the SDK now loads inside `AnthropicClient.__init__` via `_import_anthropic_sdk()`. `engine.core.agent` cold-import time 1262 ms → 146 ms (8.6×). The `anthropic` package still required at runtime; the change shifts when the cost is paid. |
| `engine.core.agent` (2026-05-14 — B-5 curator auto-trigger) | Independently authored | Added `_spawn_curator_background()` invoked from `run_conversation` on every Nth successful turn (default N=1, env `UBION_CURATOR_INTERVAL`). Wraps vendored `engine.learning.curator.maybe_run_curator()` on a daemon thread. Hermes equivalent: post-session hook / cron job. Our in-process version is Phase 1 (B) simplification; Phase 3 may move to a worker. |
| `engine.skills.__init__` (2026-05-14 — Hermes-style separation) | Independently authored | Added `_build_optional_skill_tools()` exposing `skills_search` / `skills_install` / `skills_uninstall` / `skills_installed` tools. Activates the Hub-style "not activated by default" pool: the agent starts empty and the model installs skills on demand. Provenance recorded in `<agent_home>/.hub/lock.json`. |
| `engine.storage.agent_home` (2026-05-14 — Hermes-style separation) | Independently authored | Renamed `get_bundled_skills_dir` → `get_optional_skills_dir` (shim kept). `ensure_bundled_skills_seeded` now creates `skills/{custom,installed}/` empty and exits — *no automatic seeding*. Added `list_optional_skills`, `install_optional_skill`, `uninstall_skill`, `list_installed_skills`, `seed_all_optional_skills` (manual). `skills-bundle/` directory renamed to `skills-bundle-optional/` to make the "opt-in" stance explicit. |
| `src-tauri/` (2026-05-14 — C-stage Tauri PoC) | Independently authored | Phase 3 PC tray app shell — Rust 외피 (Tauri 2.11 + tauri-plugin-shell) per PROJECT_SPEC v0.4 §2.7. Modules: `main.rs` (tray icon + menu + window close-to-tray + RunEvent::Exit cleanup), `supervisor.rs` (Python FastAPI subprocess management with `UBION_SKIP_BACKEND_SPAWN=1` opt-out). PoC measurements: 11.6 MB idle (Slack 의 ~1/40, §2.8 < 50 MB acceptance gate 압도적 통과), 13 s debug rebuild. Patterns sourced from official Tauri 2 docs (`/learn/system-tray`, `/develop/plugins on_event RunEvent::Exit`, `/develop/state-management`). Phase 3 본 패키징에서 추가될 것: 임베디드 Python (python-build-standalone), 코디네이터 websocket 클라이언트, 30분 idle hibernate, 자동 업데이터, LLM 단기 토큰 주입. |
| `engine/tools/file_ops.py` (extended 2026-05-14) | Independently authored | Added `create_workspace_file` (text + base64-binary, new-file-only policy under `UBION_WORKSPACE`). Workspace writes refuse overwrite, traversal, or out-of-root paths; reads are unrestricted. Agent home writes (write_file) remain unrestricted by design — that's the agent's own brain. |
| `engine/tools/binary_extensions.py` (2026-05-14) | Vendor copy | `tools/binary_extensions.py` (42 lines, 0-line modification). Used by file_tools / file_operations to refuse binary file reads as text. |
| `engine/tools/file_state.py` (2026-05-14) | Vendor copy | `tools/file_state.py` (332 lines, 0-line modification). Tracks file modification state across read/write operations. |
| `engine/tools/file_safety.py` (2026-05-14) | Vendor copy | `agent/file_safety.py` (111 lines; only the `_hermes_home_path` inner import rewired to `engine.storage.agent_home`). Blocks writes to .ssh, /etc/passwd, .bashrc, agent_home/.env, and other sensitive paths. |
| `engine/tools/todo_tool.py` (2026-05-14) | Vendor copy | `tools/todo_tool.py` (277 lines; only `from tools.registry` rewritten to `engine.tools.registry`). In-session task list the agent uses for planning. |
| `engine/tools/memory_tool.py` (2026-05-14) | Vendor copy | `tools/memory_tool.py` (586 lines; 3 imports rewritten — `hermes_constants` / `utils` / `tools.registry` → engine.*). MEMORY.md + USER.md persistent curated memory with add/replace/remove/read actions. |
| `engine/tools/file_tools.py` (2026-05-14) | Vendor copy | `tools/file_tools.py` (1,172 lines; 6 top-level imports rewritten — `agent.file_safety` / `tools.binary_extensions` / `tools.file_operations` / `tools.file_state` / `agent.redact` / `tools.registry` → engine.*). Four lazy `tools.terminal_tool` imports left untouched (3 wrapped in try/except, 1 in an env-manager path Phase 1 callers don't enter). |
| `engine/tools/file_operations.py` (2026-05-14) | Vendor copy | `tools/file_operations.py` (1,763 lines; 2 imports rewritten — `tools.binary_extensions` / `agent.file_safety` → engine.*). Shell-backend file ops (read/write/search/patch) shared by file_tools. |
| `engine/tools/osv_check.py` (2026-05-14) | Vendor copy | `tools/osv_check.py` (155 lines, 0-line modification). OSV.dev vulnerability check for packages the agent suggests installing. |
| `engine/bundled_skills/` seeding (Unit 14, 2026-05-14) | Independently authored | `ensure_bundled_skills_seeded()` in `engine.storage.agent_home` — idempotent per-folder copy from `engine/bundled_skills/` into `agent_home/skills/` on first boot. Called by `AIAgent.register_default_tools()`. User edits survive across restarts. |

### Files independently authored (Hermes-inspired, no adapted code)

These files were written using only the upstream module's docstring/intent
as reference. They do not require MIT attribution but the inspiration is
acknowledged.

| Our path | Inspiration |
|----------|-------------|
| `engine/llm/anthropic.py` | `agent/anthropic_adapter.py` (thin re-implementation, ~150 lines vs upstream 2079) |
| `engine/llm/aux_client.py` | `agent/auxiliary_client.py` (~150 lines vs upstream 4,179). Exposes signature-compatible `call_llm` and `_is_connection_error` so vendored context_compressor lands unchanged; routes through our AnthropicClient. Module named `aux_client` not `aux` because `aux` is a reserved Windows DOS device name. |
| `engine/tools/skill_view.py` | `tools/skills_tool.py` (schema + intent only) |
| `engine/run_demo.py` | Unit 2 smoke test, no upstream counterpart |
| `engine/__init__.py` and subpackage `__init__.py` files | Package scaffolding |

### MIT License (verbatim from upstream)

```
MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Our own copyright

New code in this directory (anything not listed above as adapted) is:

```
Copyright (c) 2026 Ubion ax center
```

Project-wide distribution license is decided at release time. Internal use only during Phase 1/2.
