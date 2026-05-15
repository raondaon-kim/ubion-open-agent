# Ubion Open Agent

**한국어 →** [README.ko.md](README.ko.md)

> A self-evolving AI agent that lives on each user's PC.
> One installer. Embedded Python. No Docker, no shared server, no surprises.

[![Status: Phase 1 + Phase 3 P3-1 complete](https://img.shields.io/badge/status-Phase%201%20%2B%20Phase%203%20P3--1-blue)](research/phase-roadmap.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Installer: ~28 MB](https://img.shields.io/badge/installer-~28%20MB-success)](#downloads)

---

## What it is

Ubion Open Agent is the reference implementation of an *internal* AI agent platform where every employee gets their own dedicated, self-improving agent — not a shared chatbot, not a workflow builder, but a personal assistant that **learns your habits, writes skills for itself, and curates its own memory** as you use it.

The architecture follows a single rule we call **Process-per-PC**: the agent's brain (LLM calls, tools, memory, skills) runs entirely in the user's machine inside a Tauri shell that wraps an embedded Python interpreter. A thin coordinator server only handles authentication, routing, and an internal LLM key pool — it never sees your conversations.

```
┌─────────────────────────────────────────────────────────────┐
│ Each user's PC                                              │
│                                                             │
│   ┌───────────────────────────────┐   ┌─────────────────┐   │
│   │ Tauri shell (Rust)            │   │ Coordinator     │   │
│   │  - tray icon                  │←→─│ (optional, P3-2)│   │
│   │  - WebView2 + React UI        │   │  - auth         │   │
│   │  - 30-min idle shutdown       │   │  - LLM keys     │   │
│   │  - signed auto-updater        │   │  - mobile relay │   │
│   ├───────────────────────────────┤   └─────────────────┘   │
│   │ Python core (embedded 3.13)   │           ↑             │
│   │  - FastAPI on free port       │      no chat data       │
│   │  - AIAgent loop               │                         │
│   │    (LiteLLM / Anthropic /     │                         │
│   │     DeepSeek)                 │                         │
│   │  - skills + memory + curator  │                         │
│   │  - delegate_task subagents    │                         │
│   └───────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Highlights

- **~28 MB installer.** LZMA-compressed NSIS .exe; sub-1-second cold start; ~95 MB RAM when active, ~24 MB when idle (Python self-terminates after 30 min and respawns on next message).
- **Install anywhere.** NSIS `currentUser` mode — no admin rights, user picks any path, **zero penalty** because all resources are resolved through Tauri's `BaseDirectory::Resource` and all data lives in `%LOCALAPPDATA%\Ubion_Agent\` plus `~/.ubion-agent/`.
- **One LLM gateway.** When a `LITELLM_BASE_URL` + `LITELLM_API_KEY` pair is configured (typical for internal company proxies), every model — Claude, DeepSeek, anything else the proxy fronts — routes through the same OpenAI-compatible endpoint. Falls back to direct Anthropic / DeepSeek SDKs when those env vars aren't set, so the same code runs in both internal and BYO-key deployments.
- **Real token streaming.** The UI streams every assistant chunk via SSE — text and DeepSeek `reasoning_content` thinking previews on separate channels — so a 30-second reasoning burst is visible in real time instead of looking like a frozen spinner.
- **Self-evolving skills with subagents.** The agent reads from 86 bundled starter skills (lazy-installed) and writes its own SKILL.md files for repeated patterns. For multi-step tasks it can spawn focused child agents via `delegate_task`, with a depth cap of 2 and a per-child fresh iteration budget. The curator loop is imported from [Hermes Agent](https://github.com/NousResearch/hermes-agent).
- **Talks to the user every turn.** A system-prompt operating rule forces one short Korean status line per turn, so the UI never goes silent during long tool chains. Skill routing is primed via a keyword table (`PPT → powerpoint`, `다이어그램 → architecture-diagram`, ...) so the right skill loads on the first turn.
- **Native, debuggable tools.** `patch` and `search_files` are pure-Python (pathlib + difflib + line-aligned fuzzy match) instead of Hermes' sandbox-shell path, so they actually work on Windows without a vendored terminal backend. `create_workspace_file` + `append_file` handle large artifacts via chunked writes. `shell` results surface stdout/stderr previews directly in the server log so failures are diagnosable from outside the agent.
- **Conversations as Markdown.** Every chat is one human-readable .md file under `.ubion-agent/conversations/`. Grep your own history. Move to a new PC by copying one folder.
- **Workspace policy: create-only, enforced.** The agent can *read* any file under `UBION_WORKSPACE` and *create* new ones, but never modifies or deletes existing files — preserving the human's work as the source of truth. The same rule is repeated in the system prompt and enforced by the file-operations layer; `patch` flat-out refuses workspace targets.
- **Tauri 2 + React 19 + Tailwind 4** on the frontend; **FastAPI + OpenAI SDK (LiteLLM) + Anthropic SDK + python-build-standalone** on the backend. No Electron, no Docker, no PyInstaller.

---

## Quick start (end user)

1. **Download** the latest installer from [Releases](https://github.com/raondaon-kim/ubion-open-agent/releases) (~28 MB).
2. **Double-click** `Ubion_Agent_<ver>_x64-setup.exe`. NSIS will ask where to install — anywhere is fine. (The installer filename is ASCII so it works on Windows accounts with non-ASCII usernames.)
3. **First-boot env seeding.** On first launch the app copies a bundled `engine/.env.bundled` into `~/.ubion-agent/.env`, which contains the LLM gateway URL and key for internal deployments. If you're running an external build, create the file yourself:
   ```env
   # Internal LiteLLM proxy (preferred — single audit trail)
   LITELLM_BASE_URL=http://your-proxy:4000
   LITELLM_API_KEY=sk-...
   ANTHROPIC_MODEL=claude-sonnet-4-6
   DEEPSEEK_MODEL=deepseek-v4-flash

   # Or direct provider keys (router falls back when LiteLLM vars are unset)
   # ANTHROPIC_API_KEY=sk-ant-...
   # DEEPSEEK_API_KEY=sk-...
   ```
4. **Launch** "Ubion Agent" from Start menu / tray icon. Send your first message. Done.

The workspace defaults to `~/Documents/Ubion 에이전트` and can be changed from the Settings screen at any time — the chosen path is written back to `.env` as `UBION_WORKSPACE`.

For uninstallation: Settings → Apps & features → "Ubion Agent". User data in `~/.ubion-agent\` is preserved.

Full operations guide: [research/phase-3-pc-install-guide.md](research/phase-3-pc-install-guide.md).

---

## Quick start (developer)

Prereqs:
- **Rust** 1.77+ (`rustup default stable`)
- **Node.js** + **pnpm** (for the web UI)
- **Python** 3.13 for dev runs (production uses the embedded interpreter)
- **Windows** for now (macOS / Linux land in Phase 4 — `docs/BUILDING_MACOS.md` documents the path)

```powershell
# 1. Clone
git clone https://github.com/raondaon-kim/ubion-open-agent.git
cd ubion-open-agent

# 2. Backend deps + API keys
python -m pip install -r src-tauri/requirements.txt
copy .env.example .env
# Edit .env — set LITELLM_BASE_URL+LITELLM_API_KEY (internal),
# or ANTHROPIC_API_KEY / DEEPSEEK_API_KEY (BYO).

# 3. Frontend deps
cd web
pnpm install
cd ..

# 4. (One-time) prepare the embedded payload for production builds
pwsh src-tauri/scripts/build-payload.ps1

# 5. Dev mode — Tauri shell + Vite HMR + Python backend, all auto-restarted
cd src-tauri
cargo tauri dev
```

To produce the standalone installer (~28 MB):

```powershell
# TMP on a drive with > 1 GB free, otherwise NSIS makensis errors out.
$env:TMP = "D:\tauri-tmp"
$env:TEMP = "D:\tauri-tmp"
# Signing key (auto-updater). One-time generation:
#   cargo tauri signer generate -w src-tauri/.tauri/updater.key --password ""
$env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content src-tauri/.tauri/updater.key -Raw).Trim()
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""

cd src-tauri
cargo tauri build --bundles nsis
# → src-tauri/target/release/bundle/nsis/Ubion_Agent_0.1.0_x64-setup.exe
```

When iterating on the engine, copy your `engine/` changes into `src-tauri/engine/` before building (or use the included `robocopy /MIR` workflow); the Tauri bundler reads from the latter as `bundle.resources`.

---

## Architecture

| Layer | Tech | Responsibility |
|---|---|---|
| Shell (PC) | Rust + Tauri 2.11 | Tray, WebView2, free-port spawn, idle shutdown / respawn, signed auto-updater |
| Embedded runtime | python-build-standalone 3.13 | Ships inside the bundle so users need nothing pre-installed |
| Engine (PC) | FastAPI + custom agent loop | AIAgent, tool dispatch, prompt builder, session DB, skill index, delegate_task subagents |
| LLM clients | `LiteLLMClient` (default when configured), `AnthropicClient`, `DeepSeekClient` | Routed by `engine/llm/router.py`; LiteLLM mode collapses every provider onto one audited gateway. 16K-token output cap with a per-turn truncation guard. |
| Streaming | Server-Sent Events | `chat_stream()` forwards `text_delta` and `reasoning_delta` chunks so the UI shows thinking previews as they arrive |
| UI (PC) | React 19 + Vite + Tailwind 4 | Single-page chat client served from `web/dist/` or Vite dev server; reasoning previews + per-turn ProgressHint |
| Persistence | Markdown + SQLite (vendored) | Conversations as .md, session DB for skill-usage learning |
| Coordinator *(future, P3-2)* | Rust (axum) | Auth, user-id → PC routing, LLM key pool, updater manifest, mobile relay |

The full spec lives in [PROJECT_SPEC.md](PROJECT_SPEC.md). The lightness budget (§2.8) — installer ≤ 60 MB, cold start < 3 s, idle RAM < 50 MB — is what every architectural decision is checked against.

---

## Engine details

A short index for contributors who skim:

- **System prompt order** (see `engine/core/agent.py:_build_system_prompt`):
  `_OPERATING_RULES` → SOUL.md → `<available_skills>` index → workspace context files → memory provider. Small models attend to the head; the operating rules live there so persona drift can't override them.
- **`_OPERATING_RULES`** enforces (1) one short Korean status sentence per turn and (2) build artifacts go to the workspace via `create_workspace_file` / `append_file` / `patch`, not `write_file` (which is reserved for the agent home).
- **Truncation guard** (`engine/core/agent.py`): when `stop_reason == "length"` AND the response carried tool_calls, the loop drops the calls (their JSON arguments almost certainly didn't survive the cut) and injects a user-role nudge asking the model to retry with a smaller payload — splitting via `append_file` or generating files from a shell script.
- **`delegate_task`** (`engine/tools/delegate.py`): spawn focused child agents in a fresh conversation. Depth-capped at 2. Children inherit the parent's tools minus `delegate_task` itself and `memory`. Per-child `IterationBudget`. Used in practice for "visually inspect this generated artifact" passes.
- **Native `patch`** (`engine/tools/file_ops.py:patch_file`): exact match → line-aligned whitespace-tolerant match → `difflib.get_close_matches` hint on no match. Workspace files are refused; trailing-newline preservation built in. Replaces the Hermes `tools.terminal_tool`-routed implementation that died on import in environments without the vendored shell backend.
- **`shell` result logging**: `tool_dispatch._summarize_result` surfaces the first 200 characters of `stdout` / `stderr` / `error` / `_warning` / `_hint` / `message` in `server.log`, so failures are debuggable from outside the running session.

---

## Repository layout

```
.
├── engine/                    # Python agent core (multi-provider, self-evolving)
│   ├── core/                  # AIAgent loop, tool dispatch, prompt builder
│   ├── llm/                   # litellm_client.py, anthropic.py, deepseek.py, router.py
│   ├── server/                # FastAPI app + __main__ entry
│   ├── skills/                # Skill registry + index cache (writable + bundled-optional union)
│   ├── tools/                 # File ops, patch, search_files, delegate, todo, memory, shell, …
│   ├── learning/              # Curator, model metadata, context engine
│   └── storage/               # agent_home, session_db, conversations (.md)
├── web/                       # React 19 + Vite + Tailwind 4 web UI (streaming chat)
├── src-tauri/                 # Rust shell + Python bundler
│   ├── src/                   # main.rs, supervisor.rs
│   ├── scripts/               # build-payload.ps1 (reproducible payload)
│   ├── capabilities/          # Tauri ACL
│   └── icons/                 # App icons
├── skills-bundle-optional/    # 86 starter skills (apple/, devops/, ml/, …)
├── tests/unit/                # pytest suite
├── docs/                      # BUILDING_MACOS.md, install guides
├── research/                  # Phase notes, decisions, retrospectives
├── sandbox/                   # Throwaway experiments (mostly gitignored)
├── .env.example               # Template for API keys / LiteLLM endpoint
├── PROJECT_SPEC.md            # Single source of truth for architectural decisions
└── AGENT.md                   # Conventions every contributing agent reads first
```

---

## Roadmap

| Phase | Status | Outcome |
|---|---|---|
| **Phase 0** | ✅ done | Engine port from Hermes, multi-provider scaffolding |
| **Phase 1 (B)** | ✅ done | Working web UI, LiteLLM-routed multi-provider, real token streaming, conversation persistence, 86 optional skills, custom-skill creation by curator, subagent delegation, OPERATING_RULES system prompt |
| **Phase 3 P3-1** | ✅ done | Tauri + embedded Python; signed installer; user-chosen install path; OS-aware workspace default; idle shutdown; auto-updater wired |
| **Phase 3 P3-2** *(coordinator)* | 🚧 next | Rust axum server: SSO, user → PC routing, LLM key pool, updater manifest, mobile relay |
| **Phase 4** | ⏳ | macOS / Linux bundles, multi-tenant operations |

Detailed phase notes: [research/phase-roadmap.md](research/phase-roadmap.md).

---

## Contributing

Open an issue or PR — but please read [AGENT.md](AGENT.md) first; it captures the conventions every contributor (human or AI agent) follows in this repo. The most load-bearing of those:

- **Look at official docs before writing framework-specific code.** Especially Tauri, Rust, and DeepSeek thinking-mode tool calling. Pattern-matching from training data costs more build cycles than reading docs costs minutes.
- **Workspace files are create-only.** Anything in the user's working folder gets read, never modified. `patch` enforces this in code; the system prompt repeats it.
- **Don't auto-seed.** The 86 starter skills are *available* but not installed — explicit `skills_install` only.
- **Don't break the silence rule.** Every turn must include one short status sentence to the user. Tool calls alone read as a hung UI.

---

## License

[MIT](LICENSE). See [engine/NOTICE.md](engine/NOTICE.md) for third-party attribution — most directly the [Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT) by Nous Research, whose curator loop and SKILL.md convention shaped the engine.

---

<a id="downloads"></a>
## Downloads

Latest builds: [Releases](https://github.com/raondaon-kim/ubion-open-agent/releases)
Issues / feedback: [Issues](https://github.com/raondaon-kim/ubion-open-agent/issues)
