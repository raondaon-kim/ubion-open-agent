# Ubion Open Agent

**한국어 →** [README.ko.md](README.ko.md)

> A self-evolving AI agent that lives on each user's PC.
> One installer. Embedded Python. No Docker, no shared server, no surprises.

[![Status: Phase 1 + Phase 3 P3-1 complete](https://img.shields.io/badge/status-Phase%201%20%2B%20Phase%203%20P3--1-blue)](research/phase-roadmap.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Installer: 24.85 MB](https://img.shields.io/badge/installer-24.85%20MB-success)](#downloads)

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
│   │  - AIAgent loop (Anthropic /  │                         │
│   │    DeepSeek)                  │                         │
│   │  - skills + memory + curator  │                         │
│   └───────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Highlights

- **24.85 MB installer.** LZMA-compressed NSIS .exe; sub-1-second cold start; ~95 MB RAM when active, ~24 MB when idle (Python self-terminates after 30 min and respawns on next message).
- **Install anywhere.** NSIS `currentUser` mode — no admin rights, user picks any path, **zero penalty** because all resources are resolved through Tauri's `BaseDirectory::Resource` and all data lives in `%LOCALAPPDATA%\.ubion-agent\`.
- **Multi-provider LLM out of the box.** DeepSeek V4 Flash by default, Claude 4 (Opus / Sonnet / Haiku) optional. Switch mid-conversation; the next turn uses the new model.
- **Self-evolving skills.** Imports the [Hermes Agent](https://github.com/NousResearch/hermes-agent) curator loop — the agent writes its own SKILL.md files based on usage patterns. 86 optional starter skills are bundled separately and installed on demand.
- **Conversations as Markdown.** Every chat is one human-readable .md file under `.ubion-agent/conversations/`. Grep your own history. Move to a new PC by copying one folder.
- **Workspace policy: create-only.** The agent can *read* any file under `UBION_WORKSPACE` and *create* new ones, but never modifies or deletes existing files — preserving the human's work as the source of truth.
- **Tauri 2 + React 19 + Tailwind 4** on the frontend; **FastAPI + Anthropic SDK + OpenAI SDK + python-build-standalone** on the backend. No Electron, no Docker, no PyInstaller.

---

## Quick start (end user)

1. **Download** the latest installer from [Releases](https://github.com/raondaon-kim/ubion-open-agent/releases) (≈ 25 MB).
2. **Double-click** `Ubion 에이전트_<ver>_x64-setup.exe`. NSIS will ask where to install — anywhere is fine.
3. **Create the API-key file** at `%LOCALAPPDATA%\.ubion-agent\.env`:
   ```env
   DEEPSEEK_API_KEY=sk-...
   # ANTHROPIC_API_KEY=sk-ant-...   # optional
   ```
4. **Launch** "Ubion 에이전트" from Start menu / tray icon. Send your first message. Done.

For uninstallation, settings → Apps & features → "Ubion 에이전트". User data in `.ubion-agent\` is preserved.

Full operations guide: [research/phase-3-pc-install-guide.md](research/phase-3-pc-install-guide.md).

---

## Quick start (developer)

Prereqs:
- **Rust** 1.77+ (`rustup default stable`)
- **Node.js** + **pnpm** (for the web UI)
- **Python** 3.13 for dev runs (production uses the embedded interpreter)
- **Windows** for now (macOS / Linux land in Phase 4)

```powershell
# 1. Clone
git clone https://github.com/raondaon-kim/ubion-open-agent.git
cd ubion-open-agent

# 2. Backend deps + API keys
python -m pip install -r src-tauri/requirements.txt
copy .env.example .env
# Edit .env to add DEEPSEEK_API_KEY (or ANTHROPIC_API_KEY)

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

To produce the standalone installer (≈ 25 MB):

```powershell
# TMP on a drive with > 1 GB free, otherwise NSIS makensis errors out.
$env:TMP = "D:\tauri-tmp"
$env:TEMP = "D:\tauri-tmp"
# Signing key (auto-updater). One-time generation:
#   cargo tauri signer generate -w src-tauri/.tauri/updater.key --password ""
$env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content src-tauri/.tauri/updater.key -Raw).Trim()
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""

cd src-tauri
cargo tauri build
# → src-tauri/target/release/bundle/nsis/Ubion 에이전트_0.1.0_x64-setup.exe
```

---

## Architecture

| Layer | Tech | Responsibility |
|---|---|---|
| Shell (PC) | Rust + Tauri 2.11 | Tray, WebView2, free-port spawn, idle shutdown / respawn, signed auto-updater |
| Embedded runtime | python-build-standalone 3.13 | Ships inside the bundle so users need nothing pre-installed |
| Engine (PC) | FastAPI + custom agent loop | AIAgent, tools, prompt builder, session DB, skill index |
| LLM clients | Anthropic SDK, OpenAI SDK (DeepSeek-compatible) | Both routed by `engine/llm/router.py` based on the model name |
| UI (PC) | React 19 + Vite + Tailwind 4 | Single-page chat client served from `web/dist/` or Vite dev server |
| Persistence | Markdown + SQLite (vendored) | Conversations as .md, session DB for skill-usage learning |
| Coordinator *(future, P3-2)* | Rust (axum) | Auth, user-id → PC routing, LLM key pool, updater manifest, mobile relay |

The full spec lives in [PROJECT_SPEC.md](PROJECT_SPEC.md). The lightness budget (§2.8) — installer ≤ 60 MB, cold start < 3 s, idle RAM < 50 MB — is what every architectural decision is checked against.

---

## Repository layout

```
.
├── engine/                    # Python agent core (multi-provider, self-evolving)
│   ├── core/                  # AIAgent loop, tool dispatch, prompt builder
│   ├── llm/                   # anthropic.py, deepseek.py, router.py
│   ├── server/                # FastAPI app + __main__ entry
│   ├── skills/                # Skill registry + index cache
│   ├── tools/                 # File ops, todo, memory, session search, …
│   ├── learning/              # Curator, model metadata, context engine
│   └── storage/               # agent_home, session_db, conversations (.md)
├── web/                       # React 19 + Vite + Tailwind 4 web UI
├── src-tauri/                 # Rust shell + Python bundler
│   ├── src/                   # main.rs, supervisor.rs
│   ├── scripts/               # build-payload.ps1 (reproducible payload)
│   ├── capabilities/          # Tauri ACL
│   └── icons/                 # App icons (cargo tauri icon output)
├── skills-bundle-optional/    # 86 starter skills (apple/, devops/, ml/, …)
├── tests/unit/                # pytest suite
├── research/                  # Phase notes, decisions, install guide
├── sandbox/                   # Throwaway experiments (mostly gitignored)
├── .env.example               # Template for API keys
├── PROJECT_SPEC.md            # Single source of truth for architectural decisions
└── AGENT.md                   # Conventions every contributing agent reads first
```

---

## Roadmap

| Phase | Status | Outcome |
|---|---|---|
| **Phase 0** | ✅ done | Engine port from Hermes, multi-provider scaffolding |
| **Phase 1 (B)** | ✅ done | Working web UI, DeepSeek + Claude, conversation persistence, 86 optional skills, custom-skill creation by curator |
| **Phase 3 P3-1** *(PC packaging)* | ✅ done | Tauri + embedded Python; 24.85 MB signed .exe; user-chosen install path; idle shutdown; auto-updater wired |
| **Phase 3 P3-2** *(coordinator)* | 🚧 next | Rust axum server: SSO, user → PC routing, LLM key pool, updater manifest, mobile relay |
| **Phase 4** | ⏳ | macOS / Linux bundles, multi-tenant operations |

Detailed phase notes: [research/phase-roadmap.md](research/phase-roadmap.md).

---

## Why "Open"

This project is built on, and contributes back to, ideas from open agent ecosystems — most directly the [Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT-licensed) by Nous Research, whose curator loop and SKILL.md convention shaped our engine. The conventions (`SKILL.md`, `AGENT.md`, the Hermes-style explicit skill install model) are reusable across other projects. See [engine/NOTICE.md](engine/NOTICE.md) and the per-file SPDX-style headers for attribution.

We publish this under MIT so internal forks at other companies can run the same architecture without legal friction.

---

## Contributing

Open an issue or PR — but please read [AGENT.md](AGENT.md) first; it captures the conventions every contributor (human or AI agent) follows in this repo. The most load-bearing of those:

- **Look at official docs before writing framework-specific code.** Especially Tauri, Rust, DeepSeek thinking-mode tool calling. Pattern-matching from training data costs more build cycles than reading docs costs minutes.
- **Workspace files are create-only.** Anything in the user's working folder gets read, never modified.
- **Don't auto-seed.** The 86 starter skills are *available* but not installed — explicit `skills_install` only.

---

## License

[MIT](LICENSE). See [engine/NOTICE.md](engine/NOTICE.md) for third-party attribution (Hermes Agent and its dependencies).
