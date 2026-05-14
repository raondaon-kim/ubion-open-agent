# Ubion Open Agent

**English →** [README.md](README.md)

> 사용자 PC 안에서 동작하는 자기진화 AI 에이전트.
> 설치 파일 하나, 임베디드 Python. Docker 도, 공유 서버도, 깜짝 놀랄 일도 없음.

[![상태: Phase 1 + Phase 3 P3-1 완료](https://img.shields.io/badge/status-Phase%201%20%2B%20Phase%203%20P3--1-blue)](research/phase-roadmap.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![설치파일: 24.85 MB](https://img.shields.io/badge/installer-24.85%20MB-success)](#%EB%8B%A4%EC%9A%B4%EB%A1%9C%EB%93%9C)

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
│   │  - AIAgent 루프 (Anthropic /   │                       │
│   │    DeepSeek)                  │                        │
│   │  - skills + memory + curator  │                        │
│   └───────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 핵심 특징

- **24.85 MB 설치파일.** LZMA 압축된 NSIS .exe; 1초 미만 부팅; 활성 시 ~95 MB / idle 시 ~24 MB (Python 이 30분 후 자기 종료, 다음 메시지에 자동 재시작).
- **어디든 설치 가능.** NSIS `currentUser` 모드 — 관리자 권한 불필요, 사용자가 임의 경로 선택, **페널티 0**. 리소스는 Tauri 의 `BaseDirectory::Resource` 로, 데이터는 모두 `%LOCALAPPDATA%\.ubion-agent\` 에 격리.
- **멀티 프로바이더 LLM 기본 내장.** 기본값은 DeepSeek V4 Flash, Claude 4 (Opus / Sonnet / Haiku) 선택 가능. 대화 중간에 바꾸면 다음 턴부터 자연스럽게 새 모델로 동작.
- **자기진화 스킬.** [Hermes Agent](https://github.com/NousResearch/hermes-agent) 의 큐레이터 루프를 차용 — 에이전트가 사용 패턴을 보고 자기 SKILL.md 를 직접 작성. 86개 시드 스킬은 별도 번들로 제공되어 *명시적 설치* 시에만 활성화.
- **대화 = Markdown 파일.** 모든 대화가 `.ubion-agent/conversations/` 안의 .md 한 파일. 자기 대화 기록을 grep 으로 검색하거나, 폴더 하나 복사로 새 PC 이전 가능.
- **워크스페이스 정책: 생산 전용.** `UBION_WORKSPACE` 안의 파일은 *읽을* 수만 있고 *새로 만들기* 만 가능. 수정·삭제 불가 — 사람의 작업을 진실의 원천으로 보존.
- 프론트엔드: **Tauri 2 + React 19 + Tailwind 4**. 백엔드: **FastAPI + Anthropic SDK + OpenAI SDK + python-build-standalone**. Electron 없음, Docker 없음, PyInstaller 없음.

---

## 빠른 시작 (사용자)

1. [Releases](https://github.com/raondaon-kim/ubion-open-agent/releases) 에서 최신 설치파일 (약 25 MB) **다운로드**.
2. `Ubion 에이전트_<버전>_x64-setup.exe` **더블클릭**. NSIS 가 설치 경로를 묻습니다 — 아무 위치나 OK.
3. `%LOCALAPPDATA%\.ubion-agent\.env` 파일에 **API 키 작성**:
   ```env
   DEEPSEEK_API_KEY=sk-...
   # ANTHROPIC_API_KEY=sk-ant-...   # 선택
   ```
4. 시작 메뉴 / 트레이 아이콘에서 "Ubion 에이전트" **실행**. 첫 메시지 전송. 끝.

제거: 설정 → 앱 및 기능 → "Ubion 에이전트". `.ubion-agent\` 사용자 데이터는 보존됩니다.

전체 운영 가이드: [research/phase-3-pc-install-guide.md](research/phase-3-pc-install-guide.md).

---

## 빠른 시작 (개발자)

사전 요구사항:
- **Rust** 1.77+ (`rustup default stable`)
- **Node.js** + **pnpm** (웹 UI)
- 개발용 **Python** 3.13 (프로덕션은 임베디드 인터프리터 사용)
- 현재 **Windows** (macOS / Linux 는 Phase 4)

```powershell
# 1. 클론
git clone https://github.com/raondaon-kim/ubion-open-agent.git
cd ubion-open-agent

# 2. 백엔드 의존성 + API 키
python -m pip install -r src-tauri/requirements.txt
copy .env.example .env
# .env 편집해 DEEPSEEK_API_KEY (또는 ANTHROPIC_API_KEY) 입력

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

Standalone 설치파일 (약 25 MB) 생성:

```powershell
# TMP 는 여유 공간 1 GB 이상인 드라이브로. 부족하면 NSIS makensis 가 mmap 에러.
$env:TMP = "D:\tauri-tmp"
$env:TEMP = "D:\tauri-tmp"
# 서명 키 (자동 업데이트용). 최초 1회만 생성:
#   cargo tauri signer generate -w src-tauri/.tauri/updater.key --password ""
$env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content src-tauri/.tauri/updater.key -Raw).Trim()
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""

cd src-tauri
cargo tauri build
# → src-tauri/target/release/bundle/nsis/Ubion 에이전트_0.1.0_x64-setup.exe
```

---

## 아키텍처

| 레이어 | 기술 | 책임 |
|---|---|---|
| 외피 (PC) | Rust + Tauri 2.11 | 트레이, WebView2, 자유 포트 spawn, idle 종료 / 재시작, 서명된 자동 업데이트 |
| 임베디드 런타임 | python-build-standalone 3.13 | 번들 안에 동봉 — 사용자 PC 에 Python 사전 설치 불필요 |
| 엔진 (PC) | FastAPI + 자체 에이전트 루프 | AIAgent, tools, prompt builder, 세션 DB, 스킬 인덱스 |
| LLM 클라이언트 | Anthropic SDK, OpenAI SDK (DeepSeek 호환) | `engine/llm/router.py` 가 모델명 기반으로 자동 라우팅 |
| UI (PC) | React 19 + Vite + Tailwind 4 | `web/dist/` 또는 Vite dev 서버에서 서빙되는 단일 페이지 채팅 클라이언트 |
| 영속화 | Markdown + SQLite (vendored) | 대화는 .md, 세션 DB 는 스킬 사용 학습용 |
| 코디네이터 *(예정, P3-2)* | Rust (axum) | 인증, user-id → PC 라우팅, LLM 키 풀, 업데이터 manifest, 모바일 중계 |

전체 명세는 [PROJECT_SPEC.md](PROJECT_SPEC.md). 모든 아키텍처 결정의 기준이 되는 "가벼움 5 척도" (설치 ≤ 60 MB, 부팅 < 3초, idle RAM < 50 MB) 는 §2.8 참조.

---

## 리포지토리 구조

```
.
├── engine/                    # Python 에이전트 코어 (멀티 프로바이더, 자기진화)
│   ├── core/                  # AIAgent 루프, tool dispatch, prompt builder
│   ├── llm/                   # anthropic.py, deepseek.py, router.py
│   ├── server/                # FastAPI 앱 + __main__ 엔트리
│   ├── skills/                # 스킬 레지스트리 + 인덱스 캐시
│   ├── tools/                 # 파일 도구, todo, memory, session search, ...
│   ├── learning/              # 큐레이터, 모델 메타데이터, context engine
│   └── storage/               # agent_home, session_db, conversations (.md)
├── web/                       # React 19 + Vite + Tailwind 4 웹 UI
├── src-tauri/                 # Rust 외피 + Python 번들러
│   ├── src/                   # main.rs, supervisor.rs
│   ├── scripts/               # build-payload.ps1 (재현 가능 페이로드)
│   ├── capabilities/          # Tauri ACL
│   └── icons/                 # 앱 아이콘 (cargo tauri icon 출력)
├── skills-bundle-optional/    # 86개 시드 스킬 (apple/, devops/, ml/, ...)
├── tests/unit/                # pytest 묶음
├── research/                  # Phase 노트, 결정 기록, 설치 가이드
├── sandbox/                   # 일회용 실험 (대부분 gitignored)
├── .env.example               # API 키 템플릿
├── PROJECT_SPEC.md            # 아키텍처 결정의 단일 진실 출처
└── AGENT.md                   # 모든 기여 에이전트가 먼저 읽는 컨벤션
```

---

## 로드맵

| Phase | 상태 | 결과물 |
|---|---|---|
| **Phase 0** | ✅ 완료 | Hermes 에서 엔진 이식, 멀티 프로바이더 스캐폴딩 |
| **Phase 1 (B)** | ✅ 완료 | 동작하는 웹 UI, DeepSeek + Claude, 대화 영속화, 86개 시드 스킬, 큐레이터 기반 커스텀 스킬 생성 |
| **Phase 3 P3-1** *(PC 패키징)* | ✅ 완료 | Tauri + 임베디드 Python; 24.85 MB 서명된 .exe; 사용자 임의 경로 설치; idle 종료; 자동 업데이터 배선 |
| **Phase 3 P3-2** *(코디네이터)* | 🚧 다음 | Rust axum 서버: SSO, user → PC 라우팅, LLM 키 풀, 업데이터 manifest, 모바일 중계 |
| **Phase 4** | ⏳ | macOS / Linux 번들, 멀티 테넌트 운영 |

상세 phase 노트: [research/phase-roadmap.md](research/phase-roadmap.md).

---

## "Open" 이라 부르는 이유

이 프로젝트는 오픈 에이전트 생태계의 아이디어 위에 만들어졌고, 또 그쪽으로 돌려보냅니다. 가장 직접적으로는 Nous Research 의 [Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT 라이선스) — 그들의 큐레이터 루프와 SKILL.md 컨벤션이 우리 엔진을 형성했습니다. 컨벤션 (`SKILL.md`, `AGENT.md`, Hermes 식 명시적 스킬 설치 모델) 은 다른 프로젝트에서도 재사용 가능합니다. 출처는 [engine/NOTICE.md](engine/NOTICE.md) 와 각 파일의 SPDX-style 헤더 참조.

다른 회사의 사내 fork 가 법적 마찰 없이 같은 아키텍처를 돌릴 수 있도록 MIT 로 공개합니다.

---

## 기여하기

이슈나 PR 환영 — 단 [AGENT.md](AGENT.md) 먼저 읽어주세요. 모든 기여자 (사람·AI 에이전트 포함) 가 따르는 컨벤션이 정리되어 있습니다. 그 중 가장 중요한 것:

- **프레임워크 특화 코드 작성 전 공식 문서 먼저.** 특히 Tauri, Rust, DeepSeek thinking-mode 도구 호출. 학습 데이터에서 패턴 매칭하는 비용 > 문서 읽는 비용.
- **워크스페이스 파일은 생산 전용.** 사용자 작업 폴더의 파일은 읽기만, 수정·삭제 금지.
- **자동 시드 금지.** 86개 시드 스킬은 *사용 가능* 하지만 자동 설치 안 함 — 명시적 `skills_install` 만.

---

## 라이선스

[MIT](LICENSE). 제3자 라이선스 표기는 [engine/NOTICE.md](engine/NOTICE.md) (Hermes Agent 및 그 의존성) 참조.

---

<a id="다운로드"></a>
## 다운로드

최신 빌드: [Releases](https://github.com/raondaon-kim/ubion-open-agent/releases)
이슈 / 피드백: [Issues](https://github.com/raondaon-kim/ubion-open-agent/issues)
