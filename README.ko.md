# Ubion Open Agent

**English →** [README.md](README.md)

> 사용자 PC 안에서 동작하는 자기진화 AI 에이전트.
> 설치 파일 하나, 임베디드 Python. Docker 도, 공유 서버도, 깜짝 놀랄 일도 없음.

[![상태: Phase 1 + Phase 3 P3-1 완료](https://img.shields.io/badge/status-Phase%201%20%2B%20Phase%203%20P3--1-blue)](research/phase-roadmap.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![설치파일: 약 28 MB](https://img.shields.io/badge/installer-~28%20MB-success)](#%EB%8B%A4%EC%9A%B4%EB%A1%9C%EB%93%9C)

---

## 무엇인가

Ubion Open Agent 는 *사내* AI 에이전트 플랫폼의 레퍼런스 구현입니다. 직원 한 명에 자기진화 에이전트 한 개 — 공유 챗봇도 아니고, 워크플로 빌더도 아닙니다. **사용자의 습관을 학습하고, 자기 스킬을 스스로 작성하고, 자기 메모리를 큐레이션** 하는 개인 비서입니다.

설계 원칙은 단 하나, **Process-per-PC** 입니다. 에이전트의 두뇌(LLM 호출·도구·메모리·스킬) 는 모두 사용자 PC 안의 Tauri 외피와 임베디드 Python 인터프리터에서 돕니다. 사내 코디네이터 서버는 인증·라우팅·LLM 키 풀만 담당 — 사용자의 대화 내용을 들여다보지 않습니다.

```
┌─────────────────────────────────────────────────────────────┐
│ 각 사용자의 PC                                                │
│                                                             │
│   ┌───────────────────────────────┐   ┌─────────────────┐   │
│   │ Tauri 외피 (Rust)              │   │ 코디네이터       │   │
│   │  - 트레이 아이콘                │←→ │ (선택, P3-2)    │   │
│   │  - WebView2 + React UI        │   │  - 인증          │   │
│   │  - 30분 idle 종료              │   │  - LLM 키 풀    │   │
│   │  - 서명된 자동 업데이터          │   │  - 모바일 중계   │   │
│   ├───────────────────────────────┤   └─────────────────┘   │
│   │ Python 코어 (임베디드 3.13)     │           ↑           │
│   │  - 자유 포트로 FastAPI          │     대화 데이터 X      │
│   │  - AIAgent 루프                │                       │
│   │    (LiteLLM / Anthropic /     │                       │
│   │     DeepSeek)                 │                        │
│   │  - skills + memory + curator  │                        │
│   │  - delegate_task 서브에이전트   │                        │
│   └───────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 핵심 특징

- **약 28 MB 설치파일.** LZMA 압축된 NSIS .exe; 1초 미만 부팅; 활성 시 ~95 MB / idle 시 ~24 MB (Python 이 30분 후 자기 종료, 다음 메시지에 자동 재시작).
- **어디든 설치 가능.** NSIS `currentUser` 모드 — 관리자 권한 불필요, 사용자가 임의 경로 선택, **페널티 0**. 리소스는 Tauri 의 `BaseDirectory::Resource` 로 해석되고, 데이터는 모두 `%LOCALAPPDATA%\Ubion_Agent\` + `~/.ubion-agent/` 에 격리.
- **LLM 게이트웨이 단일화.** `LITELLM_BASE_URL` + `LITELLM_API_KEY` 쌍이 설정되어 있으면 (사내 프록시 일반 케이스) Claude·DeepSeek 등 모든 모델이 OpenAI 호환 게이트웨이로 통일 라우팅. 두 환경변수가 없으면 Anthropic / DeepSeek SDK 직접 호출로 자동 폴백 — 사내 / BYO-key 양쪽에서 같은 코드가 작동.
- **실시간 토큰 스트리밍.** UI 가 SSE 로 모든 어시스턴트 청크를 실시간 표시 — 본문 텍스트와 DeepSeek `reasoning_content` 사고 미리보기를 별도 채널로. 30초간 사고하는 동안 멈춘 것처럼 보이지 않고 사고가 흐르는 게 보임.
- **서브에이전트로 자기진화 스킬.** 86개 시드 스킬을 인덱스에서 lazy-install 로 노출하고, 반복 패턴은 자기 SKILL.md 로 직접 작성. 다단계 작업은 `delegate_task` 로 자식 에이전트에게 위임 (depth 상한 2, 자식별 새 IterationBudget). 큐레이터 루프는 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 에서 차용.
- **매 turn 사용자에게 한 마디.** 시스템 프롬프트의 OPERATING_RULES 가 매 턴 한국어 한 줄 진행보고를 의무화 — 도구 체인이 길어져도 UI 가 침묵하지 않음. 키워드 라우팅 표 (`PPT → powerpoint`, `다이어그램 → architecture-diagram` ...) 로 첫 턴부터 맞는 스킬을 로드.
- **네이티브, 진단 가능한 도구.** `patch` 와 `search_files` 는 Hermes 의 샌드박스-셸 경로 대신 순수 Python (pathlib + difflib + 줄 단위 fuzzy match) 으로 재작성 — vendor 안 한 터미널 백엔드 없어도 Windows 에서 작동. `create_workspace_file` + `append_file` 로 대용량 산출물을 chunk 분할 작성. `shell` 결과는 stdout/stderr 미리보기가 server.log 에 직접 보여서 외부에서 진단 가능.
- **대화 = Markdown 파일.** 모든 대화가 `.ubion-agent/conversations/` 안의 .md 한 파일. 자기 대화 기록을 grep 으로 검색하거나, 폴더 하나 복사로 새 PC 이전 가능.
- **워크스페이스 정책: 생산 전용, 강제.** `UBION_WORKSPACE` 안의 파일은 *읽을* 수만 있고 *새로 만들기* 만 가능. 수정·삭제 불가. 같은 규칙이 시스템 프롬프트와 파일 도구 레이어 양쪽에 박혀 있어 — `patch` 는 워크스페이스 대상을 단호히 거부.
- 프론트엔드: **Tauri 2 + React 19 + Tailwind 4**. 백엔드: **FastAPI + OpenAI SDK (LiteLLM) + Anthropic SDK + python-build-standalone**. Electron 없음, Docker 없음, PyInstaller 없음.

---

## 빠른 시작 (사용자)

1. [Releases](https://github.com/raondaon-kim/ubion-open-agent/releases) 에서 최신 설치파일 (약 28 MB) **다운로드**.
2. `Ubion_Agent_<버전>_x64-setup.exe` **더블클릭**. NSIS 가 설치 경로를 묻습니다 — 아무 위치나 OK. (설치 파일명은 한글 사용자 경로 (예: `김용현`) 에서도 WiX 버그 없이 동작하도록 ASCII 입니다.)
3. **첫 부팅 환경변수 시드.** 앱이 처음 실행될 때 번들에 동봉된 `engine/.env.bundled` 을 `~/.ubion-agent/.env` 로 자동 복사 — 사내 빌드의 경우 LLM 게이트웨이 URL/키가 포함되어 있습니다. 외부 빌드라면 직접 작성:
   ```env
   # 사내 LiteLLM 프록시 (권장 — 단일 audit trail)
   LITELLM_BASE_URL=http://your-proxy:4000
   LITELLM_API_KEY=sk-...
   ANTHROPIC_MODEL=claude-sonnet-4-6
   DEEPSEEK_MODEL=deepseek-v4-flash

   # 또는 프로바이더 직접 키 (LiteLLM 환경변수가 비어 있으면 라우터가 폴백)
   # ANTHROPIC_API_KEY=sk-ant-...
   # DEEPSEEK_API_KEY=sk-...
   ```
4. 시작 메뉴 / 트레이 아이콘에서 **"Ubion Agent" 실행**. 첫 메시지 전송. 끝.

작업 폴더 기본값은 `~/Documents/Ubion 에이전트` 이며 Settings 화면에서 언제든 변경 가능 — 변경하면 `.env` 의 `UBION_WORKSPACE` 가 갱신됩니다.

제거: 설정 → 앱 및 기능 → "Ubion Agent". `~/.ubion-agent\` 사용자 데이터는 보존됩니다.

전체 운영 가이드: [research/phase-3-pc-install-guide.md](research/phase-3-pc-install-guide.md).

---

## 빠른 시작 (개발자)

사전 요구사항:
- **Rust** 1.77+ (`rustup default stable`)
- **Node.js** + **pnpm** (웹 UI)
- 개발용 **Python** 3.13 (프로덕션은 임베디드 인터프리터 사용)
- 현재 **Windows** (macOS / Linux 는 Phase 4 — `docs/BUILDING_MACOS.md` 에 경로 정리)

```powershell
# 1. 클론
git clone https://github.com/raondaon-kim/ubion-open-agent.git
cd ubion-open-agent

# 2. 백엔드 의존성 + API 키
python -m pip install -r src-tauri/requirements.txt
copy .env.example .env
# .env 편집 — LITELLM_BASE_URL+LITELLM_API_KEY (사내) 또는
# ANTHROPIC_API_KEY / DEEPSEEK_API_KEY (BYO) 입력

# 3. 프론트엔드 의존성
cd web
pnpm install
cd ..

# 4. (최초 1회) 프로덕션 빌드용 임베디드 페이로드 준비
pwsh src-tauri/scripts/build-payload.ps1

# 5. 개발 모드 — Tauri 외피 + Vite HMR + Python 백엔드, 자동 재시작
cd src-tauri
cargo tauri dev
```

Standalone 설치파일 (약 28 MB) 생성:

```powershell
# TMP 는 여유 공간 1 GB 이상인 드라이브로. 부족하면 NSIS makensis 가 mmap 에러.
$env:TMP = "D:\tauri-tmp"
$env:TEMP = "D:\tauri-tmp"
# 서명 키 (자동 업데이트용). 최초 1회만 생성:
#   cargo tauri signer generate -w src-tauri/.tauri/updater.key --password ""
$env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content src-tauri/.tauri/updater.key -Raw).Trim()
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""

cd src-tauri
cargo tauri build --bundles nsis
# → src-tauri/target/release/bundle/nsis/Ubion_Agent_0.1.0_x64-setup.exe
```

엔진을 수정한 뒤 빌드할 때는 `engine/` 변경분을 `src-tauri/engine/` 로 복사한 후 빌드하세요 (포함된 `robocopy /MIR` 워크플로 권장) — Tauri 번들러는 `bundle.resources` 로 후자를 읽습니다.

---

## 아키텍처

| 레이어 | 기술 | 책임 |
|---|---|---|
| 외피 (PC) | Rust + Tauri 2.11 | 트레이, WebView2, 자유 포트 spawn, idle 종료 / 재시작, 서명된 자동 업데이트 |
| 임베디드 런타임 | python-build-standalone 3.13 | 번들 안에 동봉 — 사용자 PC 에 Python 사전 설치 불필요 |
| 엔진 (PC) | FastAPI + 자체 에이전트 루프 | AIAgent, tool dispatch, prompt builder, 세션 DB, 스킬 인덱스, delegate_task 서브에이전트 |
| LLM 클라이언트 | `LiteLLMClient` (설정 시 기본), `AnthropicClient`, `DeepSeekClient` | `engine/llm/router.py` 가 자동 라우팅. LiteLLM 모드는 모든 프로바이더를 단일 audit 게이트웨이로 통합. 16K 토큰 출력 한도 + 응답 잘림 가드. |
| 스트리밍 | Server-Sent Events | `chat_stream()` 이 `text_delta` 와 `reasoning_delta` 청크를 분리 채널로 전달, UI 가 사고 미리보기 실시간 표시 |
| UI (PC) | React 19 + Vite + Tailwind 4 | `web/dist/` 또는 Vite dev 서버에서 서빙되는 단일 페이지 채팅 클라이언트, reasoning 미리보기 + ProgressHint |
| 영속화 | Markdown + SQLite (vendored) | 대화는 .md, 세션 DB 는 스킬 사용 학습용 |
| 코디네이터 *(예정, P3-2)* | Rust (axum) | 인증, user-id → PC 라우팅, LLM 키 풀, 업데이터 manifest, 모바일 중계 |

전체 명세는 [PROJECT_SPEC.md](PROJECT_SPEC.md). 모든 아키텍처 결정의 기준이 되는 "가벼움 5 척도" (설치 ≤ 60 MB, 부팅 < 3초, idle RAM < 50 MB) 는 §2.8 참조.

---

## 엔진 디테일

훑어 읽는 기여자를 위한 짧은 인덱스:

- **시스템 프롬프트 순서** (`engine/core/agent.py:_build_system_prompt` 참조):
  `_OPERATING_RULES` → SOUL.md → `<available_skills>` 인덱스 → 워크스페이스 컨텍스트 파일 → 메모리 프로바이더. 작은 모델은 prompt 첫머리 attention 이 강하므로 정책 invariant 가 거기에 위치. 사용자가 SOUL 페르소나로 무엇을 정해도 OPERATING RULES 가 위.
- **`_OPERATING_RULES`** 가 강제하는 2가지: (1) 매 턴 한국어 한 줄 진행보고, (2) 빌드 산출물은 `create_workspace_file` / `append_file` / `patch` 로 워크스페이스에 — `write_file` 은 agent_home (에이전트의 두뇌) 전용.
- **응답 잘림 가드** (`engine/core/agent.py`): `stop_reason == "length"` 이면서 tool_calls 가 있으면 (JSON 인자가 거의 확실히 잘림) 도구 호출을 드롭하고 user-role 메시지로 "더 작은 페이로드로 다시 — `append_file` 분할 또는 shell 스크립트 경유" 안내 주입.
- **`delegate_task`** (`engine/tools/delegate.py`): 새 대화로 자식 에이전트 spawn. depth 상한 2. 자식은 부모 도구를 상속하되 `delegate_task` 와 `memory` 는 제외. 자식별 새 `IterationBudget`. 실전 패턴: "방금 만든 산출물 시각 검수" 위임.
- **네이티브 `patch`** (`engine/tools/file_ops.py:patch_file`): 정확 매치 → 줄 단위 whitespace-tolerant 매치 → `difflib.get_close_matches` 힌트. 워크스페이스 거부, trailing newline 자동 보존. Hermes 의 `tools.terminal_tool` 의존 구현이 import 부터 죽던 문제를 해결.
- **`shell` 결과 로깅**: `tool_dispatch._summarize_result` 가 `stdout` / `stderr` / `error` / `_warning` / `_hint` / `message` 6개 키의 첫 200자를 `server.log` 에 직접 노출. 실패 원인이 외부에서 진단 가능.

---

## 리포지토리 구조

```
.
├── engine/                    # Python 에이전트 코어 (멀티 프로바이더, 자기진화)
│   ├── core/                  # AIAgent 루프, tool dispatch, prompt builder
│   ├── llm/                   # litellm_client.py, anthropic.py, deepseek.py, router.py
│   ├── server/                # FastAPI 앱 + __main__ 엔트리
│   ├── skills/                # 스킬 레지스트리 + 인덱스 캐시 (writable + bundled-optional 통합)
│   ├── tools/                 # 파일 도구, patch, search_files, delegate, todo, memory, shell, ...
│   ├── learning/              # 큐레이터, 모델 메타데이터, context engine
│   └── storage/               # agent_home, session_db, conversations (.md)
├── web/                       # React 19 + Vite + Tailwind 4 웹 UI (스트리밍 채팅)
├── src-tauri/                 # Rust 외피 + Python 번들러
│   ├── src/                   # main.rs, supervisor.rs
│   ├── scripts/               # build-payload.ps1 (재현 가능 페이로드)
│   ├── capabilities/          # Tauri ACL
│   └── icons/                 # 앱 아이콘
├── skills-bundle-optional/    # 86개 시드 스킬 (apple/, devops/, ml/, ...)
├── tests/unit/                # pytest 묶음
├── docs/                      # BUILDING_MACOS.md, 설치 가이드
├── research/                  # Phase 노트, 결정 기록, 회고
├── sandbox/                   # 일회용 실험 (대부분 gitignored)
├── .env.example               # API 키 / LiteLLM 엔드포인트 템플릿
├── PROJECT_SPEC.md            # 아키텍처 결정의 단일 진실 출처
└── AGENT.md                   # 모든 기여 에이전트가 먼저 읽는 컨벤션
```

---

## 로드맵

| Phase | 상태 | 결과물 |
|---|---|---|
| **Phase 0** | ✅ 완료 | Hermes 에서 엔진 이식, 멀티 프로바이더 스캐폴딩 |
| **Phase 1 (B)** | ✅ 완료 | 동작하는 웹 UI, LiteLLM 라우팅 멀티 프로바이더, 실시간 토큰 스트리밍, 대화 영속화, 86개 시드 스킬, 큐레이터 기반 커스텀 스킬, 서브에이전트 위임, OPERATING_RULES 시스템 프롬프트 |
| **Phase 3 P3-1** | ✅ 완료 | Tauri + 임베디드 Python; 서명된 설치파일; 사용자 임의 경로 설치; OS-aware 워크스페이스 기본값; idle 종료; 자동 업데이터 배선 |
| **Phase 3 P3-2** *(코디네이터)* | 🚧 다음 | Rust axum 서버: SSO, user → PC 라우팅, LLM 키 풀, 업데이터 manifest, 모바일 중계 |
| **Phase 4** | ⏳ | macOS / Linux 번들, 멀티 테넌트 운영 |

상세 phase 노트: [research/phase-roadmap.md](research/phase-roadmap.md).

---

## 기여하기

이슈나 PR 환영 — 단 [AGENT.md](AGENT.md) 먼저 읽어주세요. 모든 기여자 (사람·AI 에이전트 포함) 가 따르는 컨벤션이 정리되어 있습니다. 그 중 가장 중요한 것:

- **프레임워크 특화 코드 작성 전 공식 문서 먼저.** 특히 Tauri, Rust, DeepSeek thinking-mode 도구 호출. 학습 데이터에서 패턴 매칭하는 비용 > 문서 읽는 비용.
- **워크스페이스 파일은 생산 전용.** 사용자 작업 폴더의 파일은 읽기만, 수정·삭제 금지. `patch` 도구가 코드 레벨에서 강제하고 시스템 프롬프트가 반복.
- **자동 시드 금지.** 86개 시드 스킬은 *사용 가능* 하지만 자동 설치 안 함 — 명시적 `skills_install` 만.
- **침묵 규칙 위반 금지.** 매 턴마다 사용자에게 한국어 한 줄 진행보고 의무. 도구 호출만으로는 UI 가 멈춘 것처럼 보임.

---

## 라이선스

[MIT](LICENSE). 제3자 라이선스 표기는 [engine/NOTICE.md](engine/NOTICE.md) 참조 — 가장 직접적으로는 Nous Research 의 [Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT), 그들의 큐레이터 루프와 SKILL.md 컨벤션이 엔진을 형성했습니다.

---

<a id="다운로드"></a>
## 다운로드

최신 빌드: [Releases](https://github.com/raondaon-kim/ubion-open-agent/releases)
이슈 / 피드백: [Issues](https://github.com/raondaon-kim/ubion-open-agent/issues)
