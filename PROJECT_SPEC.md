# 사내 자기진화 에이전트 플랫폼 (Self-Evolving Agent Platform)

> **PROJECT_SPEC v0.3** — Claude Code 작업 시작용 명세서
> 작성일: 2026-05-13 (v0.1, v0.2, v0.3 모두 같은 날 — 차용 시범 단일 세션에서 의제 진화)
> 작성자: ax 센터 (Ubion)
> 상태: **Phase 1 진행 중** (단위 1~2 완료). 엔진 = 자체 구현 (옵션 C, Hermes 사상+코드 차용)

---

## 0. 한 줄 정의

**사내 사용자가 각자 격리된 자기진화 에이전트를 가지고, 단일 사내 웹 채팅 UI(또는 PC 트레이 앱)을 통해 자기 에이전트와 대화하며, 그 에이전트는 사용 패턴에 따라 자동으로 skill을 생성/개선하고 memory를 큐레이션하는 멀티테넌트 플랫폼. 사내 코디네이터 서버는 인증·라우팅·스킬 마켓만 담당하고, 에이전트의 두뇌·도구·LLM 호출은 사용자 PC 의 트레이 앱(Tauri + 임베디드 Python)에서 실행된다.**

---

## 1. 프로젝트 목표

### 1.1 What — 무엇을 만드는가

- N명의 사내 사용자가 각자 1개의 전용 에이전트 인스턴스를 보유 — 인스턴스는 **사용자 PC 의 트레이 앱(Tauri + 임베디드 Python)** 으로 동작
- 인스턴스는 사용자와 함께 진화 (skill 자동 생성, memory 자동 큐레이션, user model 자동 정교화)
- 단일 사내 진입점(웹 URL 또는 트레이 앱 창)을 통해 일반 채팅 도구처럼 사용
- 사내 코디네이터 서버는 인증, 라우팅(user_id → 어느 PC), 공용 스킬 마켓, LLM 키 풀, 감사 로그 만을 담당 (얇은 컨트롤 플레인)
- 사용자는 본인 skill 작성, 본인 agent 정의 수정, MCP 서버 연결을 자율적으로 수행
- 모바일 보조 접근: 같은 사내 URL → 코디네이터 → 사용자 PC 트레이 앱으로 메시지 중계 (PC 가 켜져 있을 때만)

### 1.2 Why — 왜 만드는가

- 사내 지식 노동의 자동화 도구를 1인 1에이전트 형태로 제공
- 일반 사내 ChatGPT-스타일 도구가 제공하지 못하는 "사용자별 누적 학습" 가치 실현
- 사내 표준 SKILL.md/AGENT.md 컨벤션을 운영 인프라에 정착
- 장기적으로 사내 knowledge base + AI agent의 결합 플랫폼으로 확장

### 1.3 Why NOT — 명시적으로 만들지 않는 것

- ❌ 단일 공유 에이전트 (50명이 같은 에이전트 = 본 프로젝트의 정반대)
- ❌ 워크플로 빌더 (Dify/Flowise 유형)
- ❌ no-code 에이전트 빌더 UI (사용자는 markdown 직접 작성)
- ❌ 메신저 봇 인터페이스 (Slack/Telegram 등 — 의도적으로 제외)
- ❌ 자체 LLM 학습 인프라 (외부 API + 선택적 로컬 추론만)

---

## 2. 핵심 결정사항 (Architecture Decisions)

### 2.1 격리 모델: Process-per-PC (v0.4 갱신)

> v0.1~v0.3 의 *Container-per-User (Docker)* 결정은 v0.4 에서 *Process-per-PC* 로 대체된다. 변경 근거는 §2.7 참조.

- 사용자 1명 = 자기 PC 의 트레이 앱 1개 = `~/.ubion-agent/` 영속 디렉터리 1개
- 트레이 앱 내부에서 에이전트 엔진(Tauri 외피 + 임베디드 Python 알맹이)이 실행
- 사용자 간 데이터 격리는 **PC 경계 + OS 사용자 계정 경계** 로 보장 (강도: 컨테이너보다 더 강함 — 물리적으로 다른 머신)
- idle 시 Python 백엔드 자동 종료 (30분 미사용 → Python 프로세스 kill, Tauri 외피만 유지), 메시지 수신 시 spawn
- 사내 코디네이터 서버는 사용자 데이터를 *보관하지 않음* — user_id 와 "현재 어느 PC 가 온라인인지" 만 안다

**결정 근거**:
- 자기진화는 "이 사람과 이 에이전트가 한 쌍"일 때만 의미가 있음. 격리 없이 공유하면 한 사용자의 강화 학습이 다른 사용자 경험을 오염.
- 사용자 N명이 늘어나도 사내 서버 부담이 선형으로 증가하지 않음 — 무거운 일(LLM 호출, 도구 실행, 컨텍스트 압축)은 모두 사용자 PC 에서 발생
- Docker 의존 제거 → 사내 보안팀 검토 표면적 축소 (자율 bash 실행은 *사용자 PC 의 사용자 권한 범위* 안으로 자연 한정됨)
- 컨테이너 운영 부담(이미지 빌드/푸시/오케스트레이션/볼륨 백업) 제거 → 운영 비용 대폭 감소

### 2.2 에이전트 엔진: 자체 구현 (Hermes 사상+코드 차용)

**전략: 옵션 C — Hermes를 reference codebase로 두고, 사상은 모두 가져오되 코드는 우리 자산으로 흡수.**

- Hermes Agent (NousResearch)는 OpenClaw의 직계 후계자로, 자기진화 루프(skill 자동 생성, memory 큐레이션, FTS5 session search)가 가장 성숙하게 구현되어 있다. 본 프로젝트는 **Hermes 코드를 적극적으로 차용**하되, Hermes를 의존성으로 박지 않고 **우리 코드베이스(Python)로 흡수**한다.
- 업스트림 추적은 하지 않는다 — 한 번 차용한 코드는 우리 자산으로 본다.
- 차용 강도는 모듈별로 다르다 (`research/hermes-code-walkthrough.md` 참조):
  - **Vendor copy** — 가장 어렵고 노하우가 깊은 모듈 (skill 자동 생성, memory 큐레이션 등)
  - **Port** — 알고리즘은 동일, 우리 컨벤션으로 재작성
  - **Reference** — 동작 원리만 보고 새로 짬
  - **Drop** — 가져오지 않음 (메신저 gateway, TUI, profile, 6 terminal backend 등)
- 라이선스: Hermes는 MIT. 차용된 모든 파일에 출처와 MIT 라이선스 헤더를 부착한다 (`research/hermes-license-policy.md` 참조).
- 컨테이너 격리, `~/.hermes/` 사상의 영속 상태 디렉터리, SOUL.md/SKILL.md/MEMORY.md 컨벤션은 그대로 가져온다.

**옵션 C가 옵션 A 대비 보안적으로 강화되는 지점 (Phase 3 사내 보안팀 미팅 대비 정리)**:

1. **공급망 보안 — 차용 시점 freeze**: Hermes 업스트림 변경이 우리 통제 없이 들어오는 경로가 없다. Hermes에 새 messaging adapter, 새 LLM provider, 새 외부 통합이 추가되어도 우리 시스템에는 자동 반영되지 않는다. (커밋 `b06e9993021a8eebd891fc60d52372446315b2f0` 기준.)
2. **공격 표면 축소 — 명시적 Drop**: 25+ 메신저 adapter (Telegram/Discord/Slack/WhatsApp 등), ACP/MCP serve/oneshot CLI/webhook, 6 terminal backend (SSH/Daytona/Modal), GitHub Copilot/Google OAuth/Code Assist, Hermes dashboard, profile 시스템은 *코드 자체가 우리 트리에 없다*. 설정으로 끄는 것보다 안전 — 실수로 켜질 수 없다. (`research/hermes-code-walkthrough.md §4` 참조.)
3. **권한 최소화 — Tool 화이트리스트가 코드 레벨**: Hermes 기본 40+ tool 중 Phase 1에서 terminal + file ops만 Port. 다른 tool은 *코드에 존재하지 않음*. 또한 우리 화이트리스트 (예: file ops 경로 제한, terminal 명령 검증, rate limit) 를 차용 시점에 코드에 박을 수 있다 — Hermes 설정 시스템에 의존하지 않는다.
4. **현실 인식**: 자기진화의 핵심 가치는 *에이전트가 자율적으로 코드를 실행*하는 데서 온다. terminal tool 자체를 제거하지는 못한다. 옵션 C가 얻는 것은 *권한 자체의 제거*가 아니라 *권한을 정교하게 다듬는 통제권*이다.

### 2.3 채팅 UI: 외부 진입점만 담당

- 채팅 UI는 *얇은 진입점*만 — 메시지 입출력, SSO 인증, 사용자별 라우팅
- 진짜 로직(에이전트 실행, skill 관리, memory)은 Hermes 컨테이너 안에서 발생
- UI 선택은 **Phase 1에서 자체 wrapper로 시작, Phase 3에서 Open WebUI fork 또는 자체 정식 UI로 결정**

### 2.4 Skill 거버넌스: Git-as-source-of-truth

- 공용 사내 SKILL.md 라이브러리는 별도 Git 저장소 (읽기 전용 공용 풀)
- 사용자 인스턴스는 공용 풀을 `git pull`로 sync, 본인 영역에서 자유롭게 fork/수정
- 좋은 패턴은 PR로 공용 풀에 환원
- 자기진화로 자동 생성된 skill은 기본 private, 사용자가 명시적으로 공유 결정

### 2.5 데이터 모델: File-based, not DB-based

- markdown 파일 + JSON 메모리가 진실의 원천
- Git으로 버전 관리, 텍스트 에디터로 직접 편집 가능
- DB는 사용 안 함 (사용자 메타데이터 정도만 예외 — 코디네이터 서버에 user_id ↔ 온라인 PC 매핑 정도)
- **OpenClaw/Hermes 사상 그대로**: "your harness, your memory"

### 2.6 멀티 provider LLM (v0.3)

- Anthropic (Claude) 와 DeepSeek 둘 다 1급 지원. 모델 이름 prefix 로 router 가 분기 (`engine.llm.router`)
- 사용자가 채팅 중 모델 선택 가능
- Phase 3 부터는 사내 LLM 키 풀 → PC 에 단기 토큰 발급 방식으로 일원화 (§2.7 참조)

### 2.7 PC 클라이언트 구성: Rust 외피 + Python 알맹이 (v0.4 신규)

PC 에 설치되는 트레이 앱은 두 층으로 구성된다:

**Rust 외피 (Tauri 2.x)** — 항상 켜져 있음, idle 시 ~15 MB
- 트레이 아이콘 + 메뉴 + 자동 업데이터
- 사내 코디네이터 서버와 websocket 유지 (heartbeat, 메시지 수신, 라이센스 갱신)
- 로컬 UI 호스팅 (React 정적 빌드를 webview 에 로드)
- Python 백엔드 supervisor — spawn / health-check / kill / 자동 재기동
- 코디네이터에서 받은 LLM 단기 토큰을 Python 환경 변수로 주입

**Python 알맹이 (임베디드 python-build-standalone)** — 필요할 때만 켜짐, 활성 시 80–120 MB
- `engine/` 본체 — AIAgent, 도구, 스킬 매니저, 메모리, 컨텍스트 압축, curator
- LLM API 직접 호출 (Anthropic / DeepSeek 공식 SDK)
- 로컬 HTTP 서버 (FastAPI :자유포트) — Tauri webview 가 호출
- 30분 idle (대화 없음 + 백그라운드 작업 없음) → Rust supervisor 가 SIGTERM
- 메시지 도착 시 Rust 가 재기동 (cold start ~2-3 초)

**경계 원칙**:
- Hermes 에서 Vendor copy 한 코드는 *모두 Python 에 남음* — Rust 마이그레이션 시도하지 않는다 (비용 ≫ 이득, §언어 호환성 분석 참조)
- 도구는 100% Python — `terminal_tool` / `browser_tool` / `code_execution_tool` 등 모두
- Rust 는 *경량 supervisor + 통신 외피* 역할만

**결정 근거**: Tauri 가 Electron 의 5–10 배 가벼움. 사용자가 켜두기만 한 idle 상태에서 사내 메신저(Slack 400–800 MB)보다 압도적으로 가볍게 유지 → "무겁다고 느끼지 않을 것" NFR (§2.8) 달성의 핵심.

### 2.8 비기능 요구사항: 가벼움 (v0.4 신규, 최우선 NFR)

> "설치해서 사용하는 사용자들이 무겁다고 느끼면 안 된다" — 사용자 결정 2026-05-14.

다음 5 척도가 Phase 3 정식 출시 acceptance gate 가 된다:

| 척도 | 임계점 (사용자 인식) | 목표 (Phase 3) |
|---|---|---|
| 설치 패키지 크기 | 100 MB 넘으면 무거움 | **30–60 MB** |
| 부팅 → 트레이 아이콘 출현 | 3 초 | **1 초** |
| 부팅 → 채팅 가능 상태 | 5 초 | **3 초** |
| Idle 메모리 (Python 종료 상태) | 200 MB | **50 MB 미만** |
| Idle 메모리 (활성 상태) | 500 MB | **150 MB 미만** |
| 메시지 전송 → 첫 응답 토큰 | 2 초 | **1 초** (LLM 네트워크 라운드트립 외 우리 책임 부분) |
| UI 클릭 → 시각 반응 | 200 ms | **100 ms** |

**미준수 시 빨간 신호** — Phase 3 진입 전 반드시 충족. Phase 1 가벼움 부채(lazy import 강화, bundled_skills 분리, 스킬 인덱스 캐시) 가 이 목표를 향한 사전 정리 작업.

**향후 결정 가드** — 가벼움을 깨뜨릴 수 있는 결정과 미리 박은 가드:
- 빌트인 도구 다 채택 → lazy import 필수 (메타데이터만 부팅 시 읽음)
- Playwright / browser_tool → opt-in 다운로드, 사용자가 명시적으로 켤 때만
- code_execution sandbox (Docker) → opt-in, Docker 없으면 사용자 권한 직접 실행 폴백
- 86 스킬 frontmatter 일괄 파싱 → `.skill-index.json` 캐시 + mtime 기반 무효화
- 자기진화 curator → 사용자 활동 중엔 비활성, idle 5분 후 시작

---

## 3. 시스템 아키텍처

### 3.1 전체 구조 (v0.4 — 분할 책임 / 컨트롤 플레인 + 데이터 플레인)

```
┌─────────────────────────────────────────────────────────────────┐
│  사내 코디네이터 서버  https://agent.ubion.global                │
│  (얇은 컨트롤 플레인 — 무거운 일 안 함)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐    │
│  │ 인증 / SSO    │  │ Dispatcher   │  │ 공용 스킬 Git Repo    │    │
│  │ (OIDC)       │  │ user→PC 매핑 │  │ (skills-public)      │    │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────┘    │
│         │                 │                                      │
│  ┌──────┴────────┐  ┌─────┴────────────┐  ┌──────────────────┐   │
│  │ LLM 키 풀     │  │ 메시지 큐 / 라우트│  │ bundled_skills    │   │
│  │ 단기 토큰 발급│  │ (websocket)      │  │ download endpoint │   │
│  └───────────────┘  └─────┬────────────┘  └──────────────────┘   │
└──────────────────────────┬┴───────────────────────────────────────┘
                           │ websocket (outbound 443, mTLS)
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ PC: ax 센터     │ │ PC: 김용현       │ │ PC: 김보은       │
│ ┌─────────────┐ │ │ ┌─────────────┐ │ │ ┌─────────────┐ │
│ │Tauri 외피    │ │ │ │Tauri 외피    │ │ │ │Tauri 외피    │ │
│ │ (Rust ~15MB) │ │ │ │              │ │ │ │              │ │
│ │ - 트레이     │ │ │ │              │ │ │ │              │ │
│ │ - websocket  │ │ │ │              │ │ │ │              │ │
│ │ - supervisor │ │ │ │              │ │ │ │              │ │
│ │ - UI host    │ │ │ │              │ │ │ │              │ │
│ └──────┬──────┘ │ │ └──────┬──────┘ │ │ └──────┬──────┘ │
│        │ spawn  │ │        │        │ │        │        │
│        ▼        │ │        ▼        │ │        ▼        │
│ ┌─────────────┐ │ │ ┌─────────────┐ │ │ ┌─────────────┐ │
│ │Python engine│ │ │ │Python engine│ │ │ │Python engine│ │
│ │ (필요시만)   │ │ │ │              │ │ │ │              │ │
│ │ - AIAgent   │ │ │ │              │ │ │ │              │ │
│ │ - 도구      │ │ │ │              │ │ │ │              │ │
│ │ - LLM 호출  │ │ │ │              │ │ │ │              │ │
│ │ - skill mgr │ │ │ │              │ │ │ │              │ │
│ │ - 30분 idle │ │ │ │              │ │ │ │              │ │
│ │   →자동종료 │ │ │ │              │ │ │ │              │ │
│ └──────┬──────┘ │ │ └──────┬──────┘ │ │ └──────┬──────┘ │
│        ▼        │ │        ▼        │ │        ▼        │
│ ~/.ubion-agent/ │ │ ~/.ubion-agent/ │ │ ~/.ubion-agent/ │
│ - SOUL.md       │ │                 │ │                 │
│ - USER.md       │ │                 │ │                 │
│ - MEMORY.md     │ │                 │ │                 │
│ - skills/       │ │                 │ │                 │
│ - sessions/     │ │                 │ │                 │
│ - memory/       │ │                 │ │                 │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         │ Anthropic / DeepSeek API 직접 호출      │
         │ (코디네이터가 발급한 단기 토큰 사용)     │
         ▼                   ▼                   ▼
    ┌──────────────────────────────────────────┐
    │  LLM Providers (Anthropic / DeepSeek)    │
    └──────────────────────────────────────────┘

모바일 보조 접속:
  사내 URL → 코디네이터 → 사용자 PC 트레이 앱(websocket 중계)
  (PC 가 켜져 있고 트레이 앱이 살아 있을 때만 가능)
```

**핵심 설계 원칙**:
- **컨트롤 플레인 (코디네이터 서버)** = 인증, 라우팅, 마켓, 키 풀, 감사 로그. 가벼움. 사용자 N명 늘어도 부담 선형 증가만.
- **데이터 플레인 (PC 트레이 앱)** = 에이전트의 두뇌, 도구, 메모리, LLM 호출. 사용자 자원 직접 활용.
- 사용자 데이터(SOUL/USER/MEMORY/skills/sessions)는 사내 서버에 *복제하지 않는다* — PC 가 진실의 원천. 백업은 사용자 PC 의 git 자동 commit + 사내 NAS 동기화(Phase 4).

### 3.2 컴포넌트 명세 (v0.4 갱신)

| 컴포넌트 | 위치 | 역할 | 기술 후보 | 상태 |
|---------|------|------|----------|------|
| **Tauri 외피 (PC)** | PC | 트레이 / UI 호스트 / websocket / Python supervisor / 자동 업데이터 | Tauri 2.x (Rust) | 확정 v0.4 |
| **Python 엔진 (PC)** | PC | AIAgent + 도구 + LLM 호출 + 스킬 + 메모리 | python-build-standalone + 우리 engine/ | 확정 v0.4 |
| **로컬 React UI** | PC (Tauri webview) | 채팅 인터페이스 | React 19 + Vite + Tailwind (현재 web/ 그대로) | 확정 (Phase 1 진행 중) |
| **Auth/SSO (코디네이터)** | 사내 서버 | SSO/OIDC + 사용자 등록 | Keycloak / Okta / Google Workspace | Phase 3 결정 |
| **Dispatcher (코디네이터)** | 사내 서버 | user_id → 온라인 PC 라우팅, 메시지 중계 | Rust(axum) 또는 Go(가벼움 중시) | Phase 3 결정 |
| **LLM 키 풀 (코디네이터)** | 사내 서버 | Anthropic/DeepSeek 키 보유 + 단기 토큰 발급 | 자체 작은 서비스 | Phase 3 |
| **공용 Skill Repo** | 사내 Git | 공용 SKILL.md 관리 | Gitea / GitHub Enterprise | 확정 |
| **bundled_skills download** | 코디네이터 정적 endpoint | 86개 시드 스킬 1회 다운로드 | nginx 정적 서빙 + ETag | Phase 2 분리 작업 |
| **Persistent Storage** | **PC `~/.ubion-agent/`** | per-user 상태 영속화 | 로컬 디스크 | 확정 v0.4 |
| **백업** | PC 자동 git commit + 사내 NAS 동기화 | 사용자 데이터 보존 | rclone / restic | Phase 4 |
| **Monitoring (코디네이터)** | 사내 서버 | 사용 패턴 + LLM 비용 추적 | Prometheus + Grafana | Phase 3 |

### 3.3 PC 내부 구조 (v0.4 — 사용자 PC 의 트레이 앱 설치 + 사용자 데이터)

**설치 위치** (관리자 권한 필요 — 1회만, 그 후 사용 안 함):

```
Windows:  C:\Program Files\Ubion Agent\
macOS:    /Applications/Ubion Agent.app/
Linux:    /opt/ubion-agent/

├── ubion-agent.exe (or app)    ← Tauri 외피 (Rust 바이너리)
├── python/                      ← 임베디드 Python 3.13 (python-build-standalone)
├── engine/                      ← 우리 Python 엔진 (Hermes 차용 코드 포함)
├── ui/                          ← React 정적 빌드 (Vite build 산출물)
└── resources/                   ← 아이콘, 메타데이터
```

**사용자 데이터 위치** (관리자 권한 불필요, OS 사용자 계정 격리):

```
~/.ubion-agent/                  ← 영속 디렉터리 (envvar: UBION_AGENT_HOME 으로 변경 가능)
├── config.yaml                  ← 사용자별 모델/도구 설정
├── SOUL.md                      ← 에이전트 정체성
├── AGENTS.md                    ← 운영 규칙
├── USER.md                      ← 사용자 컨텍스트
├── MEMORY.md                    ← 큐레이션된 메모리
├── skills/                      ← 사용자 skill (자동 생성 + 수동)
│   ├── public/                  ← 공용 풀 sync (사내 Git, read-only)
│   └── custom/                  ← 본인 skill (자기진화 포함)
├── .skill-cache/                ← bundled_skills 다운로드 캐시 (ETag 기반)
├── .skill-index.json            ← frontmatter 인덱스 캐시 (mtime 기반 무효화)
├── memory/                      ← FTS5 DB (SQLite) + 메모리 큐레이션
├── sessions/                    ← 대화 히스토리 (FTS5)
├── logs/                        ← 로컬 로그 (감사 요약은 코디네이터로 전송)
└── .git/                        ← 자동 commit으로 상태 스냅샷
```

**워크스페이스** (사용자가 작업하는 대상 폴더 — 별개 개념):

```
$UBION_WORKSPACE/                ← envvar 또는 UI 에서 picker 로 선택
                                  (예: D:\poems\classical)
├── (기존 사용자 파일 — 읽기만)
└── (에이전트가 생성한 새 파일 — create-only 정책)
```

`UBION_AGENT_HOME` 은 에이전트의 두뇌, `UBION_WORKSPACE` 는 사용자의 작업 대상. 둘은 서로 *독립* — 같은 에이전트로 여러 작업 폴더를 옮겨가며 사용 가능.

### 3.4 메시지 흐름 (v0.4)

**경로 1 — 사용자가 자기 PC 에서 트레이 앱으로 직접**:
1. 트레이 앱 메뉴 클릭 → Tauri webview 가 채팅 창 표시
2. webview → 로컬 FastAPI(:자유포트) `/v1/chat/completions` 호출
3. Tauri 가 Python 백엔드 상태 확인 — kill 되어 있으면 spawn (cold ~2-3 초)
4. Python 엔진: 메시지 처리 (LLM 호출, tool 실행, skill 로딩, memory 업데이트)
5. SSE 스트리밍 응답 → webview → 사용자
6. 대화 종료 후 30분 idle → Tauri 가 Python kill

**경로 2 — 모바일에서 사내 URL 로 접속 (PC 가 켜져 있을 때)**:
1. 사용자 모바일 → `https://agent.ubion.global` (HTTPS)
2. 코디네이터의 Auth Gateway: 세션 토큰 검증, user_id 추출
3. Dispatcher: user_id 에 해당하는 PC 의 Tauri 외피와 websocket 세션 확인
   - 온라인이면 메시지 forward
   - 오프라인이면 "PC 가 꺼져 있어 응답 불가" 또는 큐 적재(옵션, Phase 4)
4. Dispatcher → Tauri 외피 (websocket) → Python 엔진 spawn → 처리 → SSE 스트림
5. Tauri 외피 → Dispatcher → 모바일 (websocket 또는 SSE)

**LLM 토큰 흐름** (Phase 3 부터):
- Tauri 외피가 시작 시 사내 LLM 키 풀에서 단기 토큰 받음 (예: 1시간 유효)
- Python 엔진 spawn 시 환경 변수로 주입
- 만료 시 Tauri 가 갱신해 Python 에 재주입 (또는 Python 재기동)
- Python 엔진은 토큰을 가지고 Anthropic / DeepSeek API 직접 호출 (코디네이터 경유 안 함)

**Phase 1 (현재) 의 단순 흐름**: 코디네이터 / 라우팅 없음. 사용자 PC 단일 프로세스로 Vite + FastAPI + engine 직접 호출. Phase 3 이전까지 이 단순 흐름 유지.

---

## 4. Phase별 구현 계획

### Phase 0: 차용 가능성 검증 (시간 제약 없음, 프로토타입 우선)

**목표**: Hermes의 핵심 모듈을 우리 코드베이스로 떼어내어 흡수할 수 있는지를 *실제 시범 포팅*으로 검증한다. 첫 시범 대상은 **skill 자동 생성 루프**.

**원칙**:
- 이 단계에서는 *프로덕션* 인프라 코드, 컨테이너 코드, 웹 UI 코드를 작성하지 않음.
- 단, **sandbox 디렉터리 (`sandbox/skill-loop-port/`)** 에서 차용 시범 포팅 코드는 작성한다. 이 코드는 격리되며, Phase 0 게이트 결과에 따라 `engine/`으로 승격하거나 폐기.
- Hermes의 가치 자체(자기진화가 업무에 유용한가)는 본 단계에서 별도 검증하지 않는다. Hermes 평판/문서/우리 사전 분석을 신뢰하고, 우리는 *차용 가능성*에 집중한다.
- 결과는 모두 `research/` 아래 markdown으로 남김.
- `Phase 1~4`의 계획 문서와 TODO는 선행 작성 가능.

**실행 체크리스트**:

**0) 시작 조건**
- [x] `.phase` 파일을 `0`으로 생성
- [ ] Phase 0 담당자, 시작일 기록 (종료일은 미정 — 차용 시범 완료 시점이 종료)
- [x] `research/` 디렉터리와 아래 산출물 파일명을 미리 확정
  - `research/phase-0-todo.md`
  - `research/phase-0-retrospective.md`
  - `research/phase-roadmap.md`
  - `research/phase-1-todo.md` ~ `phase-4-todo.md`
  - `research/hermes-message-interface.md` ✅ 완료
  - `research/security-policy-check.md`
  - `research/hermes-code-walkthrough.md` (신규 — 모듈 지도 + 차용 강도)
  - `research/hermes-license-policy.md` (신규 — MIT 헤더 정책)
  - `research/skill-loop-port-feasibility.md` (신규 — 첫 차용 시범 계획)
- [ ] sandbox 작업 위치 확정: `sandbox/skill-loop-port/`
- [ ] Hermes 차용 기준 커밋 lock (현재 shallow clone HEAD = 2026-05-13)
- [ ] 모델 제공자, 시범 포팅 1회 LLM 호출 예산 상한 기록

**1) 사전 조사 (완료/진행 중)**
- [x] `5.1 Hermes Agent의 외부 메시지 인터페이스` → `research/hermes-message-interface.md` 완료
- [ ] `research/hermes-code-walkthrough.md` 작성 — Hermes 디렉터리/모듈 지도 + 모듈별 차용 강도 (Vendor/Port/Reference/Drop)
- [ ] `research/hermes-license-policy.md` 작성 — 차용 파일에 부착할 MIT 헤더 템플릿 + 출처 표기 규칙
- [ ] `5.5 사내 보안 정책 사전 확인` 일정 확보 또는 1차 질의 수행

**2) 첫 차용 시범 — skill 자동 생성 루프**
- [ ] `research/skill-loop-port-feasibility.md` 작성
  - Hermes의 skill 자동 생성 루프 위치(파일/라인) 식별
  - 트리거 조건(시간/메시지 수/LLM 판단)
  - LLM 호출 시점과 프롬프트 구조
  - 검증/저장 로직
  - 의존성 그래프 (이 모듈이 의지하는 다른 Hermes 모듈)
  - 차용 강도 결정 (Vendor copy / Port)
  - 포팅 작업 단위 분해
- [ ] `sandbox/skill-loop-port/` 디렉터리 시드 + README
- [ ] 코드 차용 실행 — MIT 헤더 부착 + 출처 명시
- [ ] Hermes 의존성 제거 — 차용된 코드가 단독으로 import/실행 가능하도록
- [ ] **end-to-end 실행 1회 성공**:
  - 차용 코드를 호출하여 LLM API 실제 호출이 일어남
  - 결과로 *최소 1개 skill 파일*이 생성됨
  - 생성된 skill 파일을 사람이 읽고 "쓸 만하다"고 판정
- [ ] 시범 회고 작성 — 무엇이 쉬웠고 무엇이 어려웠는지, 다른 모듈에도 같은 패턴이 통할지

**3) 종료 측정**
- [ ] 차용된 코드 줄 수 / Hermes 원본 줄 수 비율
- [ ] 포팅 작업 시간 (인시)
- [ ] LLM 비용 (시범 포팅 단계)
- [ ] 의존성 절단 작업 난이도 (정성)
- [ ] 생성된 skill 품질 (정성)
- [ ] Phase 1 진입 가능성 판정

**4) 종료 산출물**
- [ ] `research/phase-0-todo.md` (재작성 완료)
- [ ] `research/phase-0-retrospective.md`
- [ ] `research/hermes-code-walkthrough.md`
- [ ] `research/hermes-license-policy.md`
- [ ] `research/skill-loop-port-feasibility.md`
- [ ] `sandbox/skill-loop-port/` — 동작하는 차용 코드 + 생성된 샘플 skill
- [ ] `research/phase-1-todo.md` 갱신 (옵션 C 반영)

**Phase 0 결정 게이트**:
- 🟢 **차용 시범 성공** — skill 자동 생성 루프를 떼어내어 독립 실행 가능, end-to-end 1회 통과, 코드 이해도 충분 → **나머지 모듈도 같은 방식으로 차용 가능하다고 판단 → Phase 1 진행**
- 🟡 **부분 성공** — 포팅은 됐지만 의존성/LLM 비용/코드 가독성 중 한 축이 불안정 → Phase 0 연장, 차용 강도 또는 첫 시범 모듈 재검토
- 🔴 **포팅 실패** — Hermes 코드가 너무 얽혀 있어서 떼어내기 자체가 비현실적 → **옵션 C 자체 재검토** (옵션 A로 후퇴: Hermes 컨테이너 그대로 + dispatcher만 자체 구현)

### Phase 1: 자체 엔진 프로토타입 (시간 제약 없음, 프로토타입 우선)

**범위**: ax 센터 로컬 1대에서 1인 동작 검증. 사내 보안팀/SSO/멀티유저 인프라는 Phase 3로 이월.

**목표**: 자체 엔진(`engine/`)으로 메시지 → LLM → tool → skill 자동 진화 루프가 단독 실행 가능한 상태. Phase 0 sandbox 시범을 본 트리로 승격하고, 메시지 처리 루프 + 최소 tool 시스템 + memory 큐레이션까지 차용.

**아키텍처**: 단일 Python 프로세스 (Phase 1 안에서는 컨테이너 불필요). docker-compose는 Phase 1 후반 또는 Phase 2 진입 시 추가.

**핵심 작업 (옵션 C — Hermes 차용 순서)**:

작업 단위는 `research/hermes-code-walkthrough.md §6 차용 우선순위`를 따른다. 각 단위는 독립 PR/세션 단위.

1. **sandbox 승격** — `sandbox/skill-loop-port/` → `engine/learning/` 정리
2. **LLM provider adapter** — Anthropic adapter Port (`agent/anthropic_adapter.py` 참고). Mock AIAgent 폐기, 실제 client로 교체
3. **메시지 처리 루프** — `run_agent.py` 분할 Port → `engine/core/agent.py` 등
4. **prompt builder + caching** — Vendor copy (`agent/prompt_builder.py`, `agent/prompt_caching.py`)
5. **trajectory + context compressor** — Vendor copy
6. **memory manager** — Vendor copy (`agent/memory_manager.py`)
7. **skill utils + preprocessing** — Vendor copy
8. **tool 시스템 — terminal + file ops만** — Port + 화이트리스트
9. **session search (FTS5)** — Port
10. **OpenAI 호환 API 서버** — Reference로 자체 작성 (aiohttp 기반)
11. **자동 git commit + snapshot** — Port

**검증 포인트**:
- [ ] 자체 엔진이 LLM 호출 + tool 실행 + 응답을 end-to-end로 처리
- [ ] skill 자동 생성/큐레이션 루프가 sandbox 시범과 동일하게 동작 (단, Mock 아닌 실제 엔진으로)
- [ ] memory 큐레이션 루프 작동 확인
- [ ] `~/.ubion-agent/` 디렉터리에 상태 영속화 정상
- [ ] 자동 git commit이 trajectory 단위로 발생

**ax 센터 외 사용자 검증은 Phase 3로 이월** (보안팀 게이트와 함께).

### Phase 2: 운영 정책 정의 (Phase 1과 병행, 1주)

**산출물**: 4개 문서

- [ ] **GOVERNANCE.md**: 사용자 이탈, 데이터 소유권, skill 공유 정책
- [ ] **SECURITY.md**: bash 실행 범위, MCP 화이트리스트, 자원 한도
- [ ] **SKILL_STANDARD.md**: 사내 SKILL.md 작성 표준, PR 프로세스
- [ ] **OPERATIONS.md**: 백업/복구/모니터링/장애 대응 절차

### Phase 3: 정식 멀티유저 인프라 (v0.4 — Tauri 패키징 + 코디네이터 서버, 3~5주)

**목표**: 5~10명이 안정적으로 사용 가능한 production 시스템. §2.8 가벼움 5 척도 acceptance gate 통과.

**작업 1 — PC 트레이 앱 (Tauri 패키징)**:
- [ ] Tauri 2.x 프로젝트 셋업 (Windows / macOS / Linux 빌드 타깃)
- [ ] python-build-standalone 임베디드 Python 통합 (자유 포트 spawn / supervisor)
- [ ] React UI 를 Tauri webview 에 호스팅 (현재 web/ 그대로 활용)
- [ ] 자동 업데이터 (`tauri-plugin-updater`, 코디네이터의 manifest 폴링)
- [ ] 코드 서명: macOS notarization, Windows EV 인증서 (사내 IT 협조)
- [ ] 설치 패키지 크기 60 MB 이하 (§2.8 acceptance)
- [ ] 30분 idle 후 Python 자동 종료 + websocket 메시지 도착 시 spawn

**작업 2 — 사내 코디네이터 서버**:
- [ ] 사내 SSO 통합 (Keycloak/Okta/Google Workspace — 사내 표준 확인 §5.4)
- [ ] Dispatcher: user_id → 온라인 PC 라우팅 (websocket 세션 관리)
- [ ] LLM 키 풀 + 단기 토큰 발급 endpoint
- [ ] bundled_skills 다운로드 endpoint (ETag/version 갱신)
- [ ] 공용 스킬 Git Repo 구축 (Gitea / GitHub Enterprise) + read-only mirror
- [ ] 감사 로그 수집 (요약만 — 메시지 본문은 PC 에만)

**작업 3 — 운영 인프라**:
- [ ] 백업 시스템: PC 의 git commit 자동화 + 주 1회 사내 NAS 동기화 (rclone)
- [ ] 모니터링: 코디네이터에서 사용자별 LLM 비용 / 활성 시간 / 메시지 수 추적
- [ ] 자기진화 메트릭: skill 생성 빈도, memory 크기 변화 (PC → 코디네이터 텔레메트리, opt-in)

**작업 4 — 게이트 통과**:
- [ ] 사내 보안팀 검토 통과 (§5.5)
  - 자율 bash 실행이 *사용자 PC 의 사용자 권한 범위 안* 으로 자연 한정됨을 명시
  - 사용자 데이터가 사내 서버에 *보관되지 않음* 을 명시
- [ ] §2.8 가벼움 5 척도 acceptance gate 통과
- [ ] 5명 베타 사용 (Phase 4 진입 전)

### Phase 4: 사내 정식 운영 (지속)

- 신규 사용자 온보딩 프로세스
- 공용 SKILL.md 라이브러리 운영 (PR 리뷰 워크플로)
- 사내 교육 자료 ("SKILL.md 작성법", "내 에이전트와 일하는 법")
- 사용 패턴 분석 → 인프라 개선
- 자기진화 모니터링 (이상 패턴 감지, rollback 메커니즘 운영)

---

## 5. 추가 조사가 필요한 항목 (Research TODO)

> **이 섹션은 Claude Code 작업 시작 직후 가장 먼저 수행해야 합니다.**
> 각 항목은 결과를 `/research/<topic>.md`에 정리할 것.

### 5.1 Hermes Agent의 외부 메시지 인터페이스 (🔴 HIGH PRIORITY)

**질문**:
- Hermes를 헤드리스로 실행하면서 외부에서 메시지를 주고받을 방법이 있는가?
- 공식 messaging gateway (Telegram/Discord 등) 외에 HTTP API가 노출되는가?
- `mcp_serve.py` 파일이 무엇이며, Hermes를 MCP server로 노출할 수 있는가?
- `gateway/`, `tui_gateway/`, `acp_adapter/` 디렉터리의 역할은?

**조사 방법**:
- Hermes 저장소 clone 후 `gateway/`, `mcp_serve.py`, `cli.py`, `run_agent.py` 코드 분석
- 공식 문서 (https://hermes-agent.nousresearch.com/docs/) 정독
- Discord 커뮤니티에 질의 (https://discord.gg/NousResearch)

**결과 형태**:
- Hermes에 메시지를 보내고 응답을 받는 정확한 인터페이스 (HTTP/stdin/socket 중 하나)
- 만약 공식 방법이 없다면, *thin wrapper*를 직접 작성하는 코드 스케치

**작업 우선순위**: ⭐⭐⭐ Phase 0 종료 시점까지 완료 필수. 이게 안 되면 Phase 1 진입 불가.

### 5.2 Hermes의 학습 루프 메커니즘 상세 분석 (🟡 MEDIUM)

**질문**:
- skill 자동 생성은 어떤 트리거로 발생하는가? (시간, 메시지 수, LLM 판단?)
- memory 큐레이션은 얼마나 자주, 어떤 LLM 호출 패턴으로 일어나는가?
- Honcho 사용자 모델링은 어떻게 구현되어 있는가?
- 자기진화 루프가 발생할 때 LLM API 호출 횟수와 토큰 소비량은?
- 사용자가 자기진화를 *끄거나 통제*할 수 있는 설정이 있는가?

**조사 방법**:
- `agent/`, `skills/` 디렉터리 코드 분석
- `cron/`, `trajectory_compressor.py` 분석
- 1주 실사용 시 로그 분석 (Phase 0과 병행)

**결과 형태**:
- `research/hermes-learning-loop.md`에 메커니즘 다이어그램 + LLM 비용 분석

### 5.3 Hermes 멀티 인스턴스 안전성 (🟡 MEDIUM)

**질문**:
- Hermes를 한 호스트에 동시에 여러 인스턴스로 실행할 때 충돌 가능성?
  - 포트 충돌, lock 파일, 글로벌 상태?
- `~/.hermes/` 경로를 환경변수로 변경 가능한가?
- 컨테이너 안에서 실행 시 알려진 이슈?

**조사 방법**:
- Hermes 코드에서 hardcoded path/port 검색
- 2개 인스턴스를 다른 디렉터리에 띄워 충돌 테스트

**결과 형태**:
- `research/hermes-multi-instance.md` + 검증 스크립트

### 5.4 사내 SSO 표준 확인 (🟡 MEDIUM)

**질문**:
- Ubion 사내에 통합 SSO 시스템이 있는가? (Google Workspace? AD? Keycloak?)
- 사내 시스템들이 OIDC/SAML 중 무엇을 표준으로 사용하는가?
- 신규 시스템 등록 절차는?

**조사 방법**:
- 사내 IT/인프라 담당자 인터뷰

**결과 형태**:
- `research/sso-integration.md`

### 5.5 사내 보안 정책 사전 확인 (🔴 HIGH PRIORITY)

**질문**:
- 사내에서 자율 bash 실행 권한을 가진 AI 에이전트를 호스팅 가능한가?
- 외부 LLM API 호출에 대한 사내 정책 (데이터 유출 우려)?
- 사용자별 격리 수준의 사내 기준?
- 데이터 잔존/삭제 정책?

**조사 방법**:
- 사내 보안팀 사전 미팅 (Phase 1 시작 전)

**결과 형태**:
- `research/security-policy-check.md` — 통과 가능성과 제약사항 정리

### 5.6 채팅 UI 후보 비교 (🟢 LOW, Phase 3 진입 전)

**질문**:
- Open WebUI를 fork해서 multi-user 기능을 끄고 외부 dispatcher로 라우팅 가능한가?
- LibreChat은 어떤가?
- 처음부터 자체 제작 시 들어가는 작업량은?

**조사 방법**:
- Open WebUI Pipelines 기능 상세 검토
- 1~2일 PoC

**결과 형태**:
- `research/chat-ui-comparison.md`

### 5.7 로컬 LLM 통합 가능성 (🟢 LOW)

**질문**:
- 자기진화 루프(memory curation, skill generation 등)는 LLM API 호출이 빈번 → 로컬 모델로 일부 대체 가능한가?
- ax 센터 보유 RTX 5060 + Qwen3-8B NVFP4 시나리오와 통합 가능한가?
- Hermes의 모델 설정에서 task별로 다른 모델 지정 가능한가?

**조사 방법**:
- Hermes의 model 설정 시스템 분석
- vLLM/Ollama 통합 테스트

**결과 형태**:
- `research/local-llm-integration.md` + 비용 시뮬레이션

---

## 6. 참고 프로젝트 (Reference Projects)

> **각 프로젝트의 의미, 그리고 본 프로젝트에서 가져다 쓸 부분을 명시.**
> Claude Code 작업 시작 시 이 섹션을 읽고 컨텍스트 잡을 것.

### 6.1 Hermes Agent — 🎯 핵심 엔진

- **URL**: https://github.com/NousResearch/hermes-agent
- **별/포크**: 128k ⭐ / 19.3k 🍴 (활발한 개발)
- **라이선스**: MIT

**프로젝트 의미**:
- OpenClaw의 직계 후계자, "the agent that grows with you"가 슬로건
- 단일 사용자 자기진화 에이전트의 가장 성숙한 OSS 구현
- 학습 루프(skill 자동 생성/개선, memory curation, FTS5 session search, Honcho user modeling) 완비
- 다양한 messaging gateway 지원 (Telegram, Discord, Slack, WhatsApp, Signal, Email)
- 6개 terminal backend (local, Docker, SSH, Daytona, Singularity, Modal) → idle hibernation 패턴 참고
- `hermes claw migrate` 명령으로 OpenClaw에서 SOUL.md/MEMORY.md/SKILLS 임포트 가능

**본 프로젝트에서 가져다 쓸 부분 (옵션 C: 사상+코드 차용, 의존성 없음)**:

차용 강도는 모듈별로 다르다. 세부는 `research/hermes-code-walkthrough.md`를 따른다.

- **Vendor copy** (그대로 복사 후 점진 수정) — 노하우가 깊은 모듈
  - skill 자동 생성 루프 (Phase 0 첫 시범 대상)
  - memory 큐레이션 / trajectory compressor
  - Honcho 사용자 모델링
- **Port** (알고리즘 동일, 우리 스타일로 재작성)
  - 메시지 처리 루프 (`agent/`)
  - FTS5 session search
  - tool 시스템 (사내 화이트리스트 적용)
  - SOUL.md/SKILL.md 파서
  - `~/.hermes/` 디렉터리 구조 (이름은 `.agent/` 등으로 변경)
- **Reference** (원리만 보고 새로 짬)
  - OpenAI 호환 API 서버 (단순 aiohttp wrapper)
  - 자기진화 메트릭 / 모니터링
- **Drop** (가져오지 않음)
  - messaging gateway (Telegram/Discord/Slack/WhatsApp/Signal — 요구사항에서 명시적 제외)
  - 공식 TUI / dashboard (진입점은 웹 UI)
  - 6 terminal backend (Docker/SSH/Daytona/Singularity/Modal — 우리는 Docker만)
  - profile 시스템 (컨테이너로 격리)
  - ACP adapter / MCP server / oneshot CLI / webhook adapter

**라이선스**: Hermes는 MIT. 차용된 모든 파일에 출처 + 라이선스 헤더를 부착한다. `research/hermes-license-policy.md` 참조.

**업스트림 추적**: 하지 않음. 차용된 코드는 우리 자산. Hermes의 후속 개선은 본 프로젝트에 자동 반영되지 않는다.

**조사 우선순위**: 🔴 HIGH — Phase 0 차용 가능성 검증의 직접 대상

---

### 6.2 OpenClaw — 📚 컨벤션의 원천

- **URL**: https://github.com/openclaw/openclaw
- **별/포크**: 145k+ ⭐
- **라이선스**: MIT

**프로젝트 의미**:
- 단일 사용자 personal AI assistant의 원형
- SOUL.md/AGENTS.md/TOOLS.md/USER.md/MEMORY.md/HEARTBEAT.md 파일 컨벤션을 정립
- markdown + SQLite만으로 모든 상태 관리 ("your harness, your memory")
- 25+ 메신저 채널 지원 (지금은 사용 안 함)

**본 프로젝트에서 가져다 쓸 부분**:
- ✅ **파일 컨벤션의 정신** — SKILL_STANDARD.md 작성 시 base reference
- ✅ **단순한 데이터 모델** (DB 없이 markdown + SQLite) — 본 프로젝트도 동일 철학
- ❌ **OpenClaw 본체** — 설치하지 않음 (Hermes가 후계자)

**참고용**: `mergisi/awesome-openclaw-agents` (https://github.com/mergisi/awesome-openclaw-agents) — 177개 SOUL.md 템플릿 모음, 사내 표준 작성 시 영감

**조사 우선순위**: 🟢 LOW (Hermes가 이미 호환)

---

### 6.3 DeerFlow (ByteDance) — 🏗️ 하네스 아키텍처 reference

- **URL**: https://github.com/bytedance/deer-flow
- **별**: 61.5k ⭐
- **라이선스**: MIT

**프로젝트 의미**:
- "Super Agent Harness"로 자기 정체화한 production-grade 시스템
- LangGraph 기반 단일 에이전트 + 11-단계 미들웨어 체인
- per-thread 격리 sandbox (Docker/K8s)
- skill progressive loading 메커니즘
- Gateway/LangGraph 분리 아키텍처

**본 프로젝트에서 가져다 쓸 부분**:
- ✅ **per-thread → per-user 격리 패턴** — 본 프로젝트는 더 강한 격리 (컨테이너 단위)
- ✅ **skill progressive loading 사상** — Hermes가 이미 비슷하게 구현했지만 reference
- ✅ **Gateway/Engine 분리 사상** — 본 프로젝트의 Dispatcher/Hermes 분리와 유사
- ❌ **DeerFlow 본체** — 사용하지 않음 (단일 사용자 long-horizon task용, 자기진화 없음)

**조사 우선순위**: 🟢 LOW (이미 분석 완료)

---

### 6.4 Open WebUI — 🖼️ UI 후보

- **URL**: https://github.com/open-webui/open-webui
- **별**: 137k+ ⭐
- **라이선스**: MIT-derived (BSD-3-Clause)

**프로젝트 의미**:
- 사내 멀티유저 ChatGPT-style 채팅 UI의 사실상 표준
- SSO/OIDC/LDAP, RBAC, multi-user day-one
- Skills System, Tools, Functions, Pipelines 확장 시스템 보유
- Workspace 단위 모델/스킬/도구 관리

**본 프로젝트에서 가져다 쓸 부분 (Phase 3에서 결정)**:
- ⚠️ **옵션 A**: fork해서 multi-user 기능을 *얇은 라우터*로 바꾸고 진입점으로만 사용
  - 장점: UI 개발 부담 0
  - 위험: Open WebUI의 multi-user는 user별로 격리된 DB 레코드만 갖는 모델 → 본 프로젝트의 컨테이너 격리와 사상 충돌, fork 유지보수 부담
- ⚠️ **옵션 B**: Pipelines로 외부 dispatcher 연결
  - 장점: fork 없이 가능
  - 위험: Pipelines는 OpenAI-compatible 응답 포맷 가정, Hermes 응답을 변환해야 함

**조사 우선순위**: ~~🟢 LOW (Phase 3 진입 시점)~~ — **v0.4 결정으로 closed**. 자체 React 19 + Vite + Tailwind 4 UI 로 확정. Open WebUI fork 검토는 폐기.

---

### 6.5 agentskills.io — 🌐 외부 skill 표준

- **URL**: https://agentskills.io (Hub) / SKILL.md 표준 사양
- **의미**: Hermes가 호환하는 외부 skill 생태계
- **본 프로젝트에서**: 사내 SKILL_STANDARD.md 작성 시 호환성 유지 (사내 skill ↔ 외부 skill 양방향 사용 가능하게)

**조사 우선순위**: 🟡 MEDIUM (Phase 2 SKILL_STANDARD.md 작성 시)

---

### 6.6 aaronjmars/soul.md — 📝 SOUL.md 빌더 reference

- **URL**: https://github.com/aaronjmars/soul.md
- **의미**: 사용자 데이터를 ingest해서 SOUL.md를 자동 생성하는 skill
- **본 프로젝트에서**: 사내 신규 사용자 온보딩 시 *"당신만의 SOUL.md 만들기"* 워크플로 참고

**조사 우선순위**: 🟢 LOW (Phase 4 온보딩 설계 시)

---

## 7. 기술 결정 매트릭스

| 결정 항목 | 선택 | 대안 | 결정 시점 | 결정 이유 |
|---------|------|------|---------|---------|
| 에이전트 엔진 | **자체 구현 (옵션 C, Hermes 사상+코드 차용)** | Hermes 그대로 사용 (옵션 A), Hermes fork (옵션 B), 사상만 차용 후 0부터 (옵션 C 강버전) | 2026-05-13 | 통제권 확보, 사내 보안/거버넌스 자유도, 학습 가치 |
| Hermes 업스트림 추적 | **하지 않음** | 정기 rebase | 2026-05-13 | 한 번 차용 후 우리 자산. fork 유지 부담 회피 |
| 엔진 구현 언어 | **Python** | TypeScript, Go | 2026-05-13 | Hermes가 Python — Port 비용 최소화 |
| Phase 0 첫 차용 모듈 | **skill 자동 생성 루프** | memory 큐레이션, FTS5 search | 2026-05-13 | 가장 위험/노하우 깊은 모듈 먼저 검증 |
| 차용 시범 작업 위치 | **`sandbox/skill-loop-port/`** | `engine/` 본 트리 | 2026-05-13 | 게이트 실패 시 폐기 용이, 본 트리 오염 방지 |
| Hermes 외부 메시지 인터페이스 (참고용) | **OpenAI 호환 API 서버 차용 (Reference)** | ACP, oneshot, MCP | 2026-05-13 | `research/hermes-message-interface.md` 결과 |
| Multi-provider LLM | **Anthropic + DeepSeek 둘 다 1급** | Anthropic 단일 | 2026-05-13 | DeepSeek 비용 효율 + 모델 다양성 |
| 채팅 UI (Phase 1) | **자체 React 19 + Vite + Tailwind 4 + Noto Sans KR** | Open WebUI fork | 2026-05-13 | 한국어 특화 + 모바일 반응형 |
| 단일 포트 정책 | **사용자=Vite 8803, 내부=FastAPI 9000** | 분리 도메인 | 2026-05-13 | CORS 0, 모바일 같은 origin |
| **격리 방식** | **Process-per-PC** (v0.4 갱신) | Container per user (v0.1~v0.3) | **2026-05-14** | **PC 자원 활용 + 사내 서버 부하 최소화 + 컨테이너 운영 부담 제거 (§2.1, §2.7)** |
| **PC 클라이언트 구성** | **Rust 외피 (Tauri) + Python 알맹이** | 순수 Python(PySide), 순수 Rust 재작성, Electron | **2026-05-14** | **Tauri idle ~15 MB vs Electron 100+ MB. Vendor copy 자산 보존. Python idle hibernate 가능 (§2.7)** |
| **Python idle 자동 종료** | **30분** | 10분 / 즉시 / 안 함 | **2026-05-14** | **업무 주기 자연스러움. wake-up cold start 2-3초 감수 가능** |
| **LLM API 키 관리 (Phase 3+)** | **사내 키 풀 + PC 단기 토큰 발급** | 사용자가 자기 키 입력 (Phase 1 현재) | **2026-05-14** | **사내 거버넌스 + 사용량 추적 가능** |
| **Python 번들 도구** | **python-build-standalone** | PyOxidizer, PyInstaller, 시스템 Python | **2026-05-14** | **uv 가 사용하는 활발 유지보수 빌드. macOS 코드 서명 처리 자연스러움** |
| Phase 1 오케스트레이션 | 단일 프로세스 (PC 1대) | Docker Compose | 2026-05-14 (갱신) | Phase 1 은 로컬 1대 1인. Phase 3 진입 시 Tauri 패키징으로 자연 전환 |
| Phase 3 오케스트레이션 | **Tauri 패키징 + 사내 코디네이터 서버** | Docker Swarm, K8s | **2026-05-14** | 위 결정들의 자연 귀결. K8s/Docker 불필요 |
| Phase 3 인증 | TBD | 사내 SSO (Keycloak / Okta / Google Workspace) | Phase 3 | 5.4 조사 결과 |
| Phase 3 코디네이터 구현 언어 | TBD | Rust(axum), Go, Node.js | Phase 3 시작 시 | 가벼움 우선 — Rust 또는 Go 유력 |
| 모델 사용 정책 | TBD | Cloud only, Hybrid, Local only | Phase 0 후속 / Phase 1 시작 시 | 5.7 조사 결과 |

---

## 8. 리스크 레지스터

| ID | 리스크 | 영향 | 발생 가능성 | 대응 |
|----|-------|-----|----------|-----|
| R1 | ~~Hermes의 외부 진입점이 깔끔하지 않음~~ | — | — | **CLOSED 2026-05-13** |
| R2 | 자기진화로 에이전트가 이상해짐 → 사용자 불만 | 🟡 Medium | 🔴 High | Phase 1부터 git commit 자동화, rollback 메커니즘 |
| R3 | LLM API 비용 폭주 | 🔴 High | 🟡 Medium | Phase 0 시범 포팅 단계에서 1회 호출 비용 측정 → Phase 1에서 50배 시뮬레이션. Phase 3 부터 사내 키 풀에서 사용자별 한도 |
| R4 | 사내 보안팀 통과 못함 | 🔴 High (Phase 3+) | 🟡 Medium | **Phase 1/2는 로컬 개발 범위 — 보안팀 게이트 비활성**. Phase 3 정식 멀티유저 인프라 시작 직전 조사 5.5 수행. v0.4 Process-per-PC 결정으로 *서버 측 자율 bash 0* — 보안 표면적 자연 축소 |
| R5 | 사내 사용자의 AI literacy 부족으로 도입 실패 | 🟡 Medium | 🟡 Medium | Phase 1에 "AI 친숙한 1명" + Phase 3 직전 "관심 없는 1명" 검증 |
| R6 | ~~멀티 인스턴스(컨테이너) 동시 실행 시 충돌~~ → v0.4 결정으로 무효화 (컨테이너 사용 안 함) | — | — | **CLOSED 2026-05-14 (구조 3)** |
| R7 | 사용자 이탈 시 데이터 처리 분쟁 | 🟡 Medium | 🟢 Low | Phase 2 GOVERNANCE.md. v0.4 결정으로 데이터가 *PC 에만* 존재 → 분쟁 단순화 |
| R8 | **Hermes 코드 차용 실패** | 🔴 High | 🟡 Medium | **CLOSED 2026-05-13 (Phase 0 GREEN)** |
| R9 | Vendor copy한 코드에 잠재 버그 발견 → 업스트림 fix를 못 받음 | 🟡 Medium | 🟡 Medium | 우리 코드로 직접 fix. 차용 시점부터 우리 자산이라는 원칙 유지 |
| R10 | 차용 코드의 MIT 라이선스 헤더 누락 → 라이선스 위반 | 🟡 Medium | 🟢 Low | `research/hermes-license-policy.md` 강제. CI에서 헤더 체크 (Phase 1) |
| R11 | 자체 엔진 구현 일정이 무한 확장 | 🟡 Medium | 🟡 Medium | Phase 0 게이트 후 Phase 1 일정 재산정. 모듈별 작업 단위 분해. 프로토타입 우선 원칙 유지 |
| **R12** | **포트 충돌** — 사용자 PC 의 우리 FastAPI 포트가 다른 앱에 점유됨 | 🟡 Medium | 🟡 Medium | **Tauri spawn 시 자유 포트 탐색 + 환경 변수로 Python 에 주입. React UI 도 주입값 사용. Phase 1 에선 8803/9000 고정, Phase 3 패키징 시 동적 전환** |
| **R13** | **OS-level 패키지 서명** — macOS notarization, Windows SmartScreen 거부, Linux GLIBC 호환성 | 🔴 High (Phase 3) | 🟡 Medium | **Phase 3 진입 직전 사내 IT 협조 확보. macOS Apple Developer 계정 + Windows EV 인증서. python-build-standalone 이 GLIBC 다중 버전 빌드 제공** |
| **R14** | **사내 방화벽 / 프록시** — outbound websocket / HTTPS 차단, 또는 모든 통신이 사내 프록시 경유 | 🟡 Medium | 🟡 Medium | **outbound 443 만으로 동작하는 설계. anthropic SDK 가 HTTPS_PROXY 환경 변수 인식. 사내 LLM 도메인 화이트리스트 — Phase 3 IT 협조** |
| **R15** | **Tauri 자동 업데이트 시 Vendor copy 라이선스 추적** | 🟢 Low | 🟢 Low | **NOTICE.md 가 패키지에 항상 포함. Tauri 업데이터가 zip 통째 교체 → 자동 보존. CI에서 NOTICE.md 누락 체크** |
| **R16** | **PC 가 꺼져 있을 때 모바일 접속 불가** | 🟡 Medium | 🔴 High | **사용자 명시: "PC 가 꺼져 있어 응답 불가" 안내. Phase 4 옵션으로 메시지 큐 적재 → PC 재기동 시 픽업 검토** |
| **R17** | **Python 30분 idle 후 종료 — 사용자가 재기동 cold start (2-3초) 를 느낌** | 🟢 Low | 🟡 Medium | **wake-up 중 "준비 중..." UI 표시. context_compressor 같은 무거운 import 는 lazy 화. Phase 1 가벼움 부채 작업으로 사전 정리** |
| **R18** | **§2.8 가벼움 5 척도 미달 — 사용자가 "무겁다" 인식** | 🔴 High (Phase 3 acceptance gate) | 🟡 Medium | **Phase 1 B-단계 가벼움 부채 3개 선행. Phase 3 진입 전 5 척도 실측. 미달 시 Phase 3 게이트 빨강 (강제 보완)** |

---

## 9. 성공 기준 (Success Criteria)

### Phase 0 종료 시 (v0.2 의제: 차용 가능성 검증)
- 🟢 **달성 (2026-05-13)** — `research/phase-0-retrospective.md`
- skill 자동 생성 루프 차용 시범 end-to-end 성공
- vendor copy + shim 패턴이 일반화 가능함을 입증
- 차용 비율 85%, 미해결 의존성 0개

### Phase 1 종료 시 (v0.2 의제: 자체 엔진 프로토타입, 로컬 1인)

**Phase 1 종료 = (A) 기술 완성도 AND (B) Goal 검증 — 순차로 둘 다 통과**

**(A) 기술 완성도 — `research/phase-1-todo.md`의 11단위 모두 종료**:
- 단위 1~2: ✅ sandbox → engine 승격 + AIAgent 골격 (완료 2026-05-13)
- 단위 3~11: 미진행. 단위 우선순위는 **기술 의존성 순서** (옵션 나)

**(B) Goal 검증 — 시 에이전트 시나리오 1주 사용**:
- 검증 시나리오: **시 에이전트 (창의/탐색 작업 축)** — `research/phase-1-demo-scenario-poet.md`
- 검증 게이트:
  - 1주 동안 ax 센터가 본 엔진과 매일 대화 (시 창작 요청, 피드백, 수정)
  - 자동 생성된 skill 최소 3개 (예: "시 톤 가이드", "사용자 취향 패턴", "수정 절차")
  - 다음 세션이 이전 세션의 결정/취향을 기억함 (memory 누적 증명)
  - 같은 요청 반복 시 첫 회 대비 사람이 추가로 손보는 양이 감소
  - 1주 누적 LLM 비용이 사전 상한 이내
- 단위 11 종료 후 본 검증 단계 진입 → 1주 사용 → Phase 1 GREEN

**순서**: 단위 1 → 2 → ... → 11 완료 → 시 에이전트 1주 사용 → Phase 1 종료.

### Phase 2 종료 시
- 4개 정책 문서 (GOVERNANCE, SECURITY, SKILL_STANDARD, OPERATIONS) 초안 완료
- Phase 3 인프라 설계 입력값 정리됨

### Phase 3 종료 시 (v0.4 갱신)

**기능 게이트**:
- 5명 베타 사용자 2주 안정 운영 (각자 자기 PC 트레이 앱 + 사내 코디네이터 통합)
- 사내 SSO 통합 완료, 단기 토큰 발급 작동
- 모바일 보조 접속 검증 (사내 URL → PC 트레이 앱 라우팅)
- 사내 보안팀 정식 승인

**가벼움 acceptance gate (§2.8 — 5 척도 실측)**:
- [ ] 설치 패키지 크기 60 MB 이하
- [ ] 부팅 → 트레이 아이콘 1 초 이하
- [ ] 부팅 → 채팅 가능 3 초 이하
- [ ] Idle 메모리 (Python 종료 상태) 50 MB 미만
- [ ] Idle 메모리 (활성 상태) 150 MB 미만
- [ ] 메시지 전송 → 첫 응답 토큰 1 초 이내 (LLM 라운드트립 외)
- [ ] UI 클릭 → 시각 반응 100 ms 이내

**미달 척도가 있으면 Phase 3 게이트 빨강** — 강제 보완 후 재측정. 정식 출시 보류.

**운영 측면**:
- 30분 idle hibernation 작동 확인 — 평소 자원 사용량 적정선
- bundled_skills 다운로드 + 캐시 검증 (재설치 시 1회만 받음)
- 사내 LLM 키 풀 + 사용자별 비용 추적 작동

### Phase 4 (6개월 후)
- 사내 사용자 10명 이상 정기 사용
- 공용 SKILL.md 30개 이상 등록
- 사용자가 자율적으로 PR로 skill 기여하는 사례 5건 이상

---

## 10. Claude Code 작업 시작 가이드

이 명세서를 가지고 Claude Code에서 작업할 때:

### 10.1 첫 세션에서 할 일

1. 이 PROJECT_SPEC.md를 작업 디렉터리에 두고 Claude Code 실행
2. `claude` 명령으로 시작 후 다음과 같이 지시:
   ```
   PROJECT_SPEC.md를 읽고, /research 디렉터리를 만들어
   섹션 5의 조사 항목들을 작업 시작 전에 수행하자.
   우선순위 🔴 HIGH 항목부터 시작.
   ```

### 10.2 작업 구조

```
project-root/
├── PROJECT_SPEC.md              ← 이 파일
├── AGENT.md                     ← Claude Code 작업 가이드 (별도 작성 권장)
├── research/                    ← 섹션 5의 조사 결과
│   ├── hermes-message-interface.md
│   ├── phase-roadmap.md
│   ├── phase-1-todo.md
│   ├── phase-2-todo.md
│   ├── phase-3-todo.md
│   ├── phase-4-todo.md
│   ├── hermes-learning-loop.md
│   ├── hermes-multi-instance.md
│   ├── sso-integration.md
│   ├── security-policy-check.md
│   ├── chat-ui-comparison.md
│   └── local-llm-integration.md
├── docs/
│   ├── GOVERNANCE.md            ← Phase 2 산출물
│   ├── SECURITY.md
│   ├── SKILL_STANDARD.md
│   └── OPERATIONS.md
├── infra/                       ← Phase 1+
│   ├── docker-compose.yml
│   ├── dispatcher/
│   ├── web-ui/
│   └── hermes-container/
└── skills-public/               ← 공용 skill repo (별도 git submodule 또는 분리)
```

### 10.3 작업 원칙

- **Phase 0 검증 게이트 통과 전에는 코드 작성 금지**. 조사와 사용만.
- **각 Phase 시작 시 PROJECT_SPEC.md를 다시 읽고 해당 Phase의 작업 목록 확인**.
- **모든 결정은 *결정 시점*에 PROJECT_SPEC의 결정 매트릭스(섹션 7) 업데이트**.
- **조사 결과는 항상 `research/` 디렉터리의 markdown 파일로 남길 것**.
- **Claude Code에 작업 위임 시 큰 단위 (Phase 단위)가 아니라 작은 단위 (조사 1건, 컴포넌트 1개) 단위로**.

---

## 11. 변경 이력

| 버전 | 날짜 | 변경 사항 | 작성자 |
|------|------|---------|--------|
| 0.1 | 2026-05-13 | 초안 작성 | ax 센터 + Claude |
| 0.2 | 2026-05-13 | **엔진 전략 변경: Hermes 그대로 사용(옵션 A) → 자체 구현 + Hermes 사상/코드 차용(옵션 C)**. Phase 0 재정의: 가치 검증 → 차용 가능성 검증. 언어 = Python. 업스트림 추적 안 함. 첫 시범 모듈 = skill 자동 생성 루프. R1 closed, R8~R11 신규 추가 | ax 센터 + Claude |
| 0.3 | 2026-05-13 | Phase 0 GREEN 판정 기록. Phase 1 종료 기준 명시화: (A) 11단위 기술 완성 + (B) 시 에이전트 1주 검증 순차. 단위 우선순위 = 기술 의존성 순서. §9 갱신 | ax 센터 + Claude |
| **0.4** | **2026-05-14** | **아키텍처 결정 전환 (구조 3 — 분할 책임)**. §2.1 Container-per-User → **Process-per-PC**. §2.7 신규 — **PC 클라이언트 = Tauri (Rust 외피) + 임베디드 Python (알맹이) + 30분 idle hibernate**. §2.8 신규 — **가벼움 NFR 5 척도 acceptance gate** (설치 60 MB, idle 50 MB, 부팅 3초 등). §3.1 도식 전면 갱신 — 사내 서버 = 얇은 컨트롤 플레인 (인증/라우팅/스킬 마켓/LLM 키 풀), 데이터 플레인 = PC. §3.3 컨테이너 디렉터리 → PC 디렉터리 (설치 + 사용자 데이터 분리). §3.4 메시지 흐름 = 경로 1 (PC 트레이 직접) + 경로 2 (모바일 → 코디네이터 → PC websocket). §4 Phase 3 = Docker/K8s → Tauri 패키징 + 코디네이터 서버 + 사내 LLM 키 풀. §7 결정 매트릭스 — 격리/PC 클라이언트/Python idle/LLM 키 풀/Python 번들/multi-provider/단일 포트/Phase 3 오케스트레이션 갱신·신규. §8 R6/R8 closed, R12~R18 신규 (포트 충돌/OS 서명/방화벽/라이선스/PC 꺼짐/wake-up/가벼움 게이트). §9 Phase 3 종료 기준에 가벼움 5 척도 게이트 추가. 결정 근거: 사용자 N명 시 사내 서버 부하 선형 증가 방지 + PC 자원 활용 + 컨테이너 운영 부담 제거 + Vendor copy 자산 보존 + "무겁다고 느끼지 않을 것" 사용자 요구 | ax 센터 + Claude |

---

## Appendix A: 용어집

- **Hermes Agent**: NousResearch가 개발한 자기진화 단일 사용자 에이전트
- **OpenClaw**: Hermes의 전신, SOUL.md/SKILL.md 컨벤션의 원천
- **SOUL.md**: 에이전트의 정체성/성격/규칙을 정의하는 markdown 파일
- **SKILL.md**: 도메인 작업을 모듈화한 markdown 파일 (frontmatter + 본문)
- **Harness**: 에이전트가 살 수 있는 환경 (파일시스템, 메모리, 도구, skill의 집합)
- **자기진화 루프 (Learning Loop)**: 에이전트가 사용 경험에서 자동으로 skill을 만들고 memory를 큐레이션하는 메커니즘
- **격리(Isolation)**: 사용자 A의 데이터/학습/skill이 사용자 B에게 영향 주지 않는 상태
- **idle hibernation**: 사용 안 하는 컨테이너를 stop시켜 자원 절약, 메시지 도착 시 wake-up
- **MCP (Model Context Protocol)**: LLM과 외부 도구를 연결하는 표준 프로토콜

---

## Appendix B: 명세 작성 시 참고한 대화 컨텍스트

본 명세서는 ax 센터와 Claude의 다음 대화를 기반으로 작성되었습니다:

1. DeerFlow 분석 → "하네스(harness)" 개념 도입
2. 사내 멀티유저 채팅 도구 요구사항 정의
3. Open WebUI / LibreChat / LobeChat 비교 → Open WebUI 선택
4. OpenClaw 확인 → 단일 사용자 하네스 사상 이해
5. Hermes Agent 발견 → "자기진화" 키워드로 요구사항 명확화
6. "1인 1 에이전트 + 자동 진화 + 사내 단일 채팅 UI" 조합 확정
7. 메신저 봇 옵션 제외 (의도적)
8. Container-per-user 아키텍처 합의
9. Phase 0~4 일정 합의

---

*끝.*
