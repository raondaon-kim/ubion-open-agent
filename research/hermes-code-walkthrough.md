# Research: Hermes Code Walkthrough — 모듈 지도 + 차용 강도 매트릭스

## 목적

본 프로젝트는 옵션 C (자체 구현 + Hermes 사상/코드 차용) 전략을 선택했다. 어느 모듈을 어떤 강도로 차용할지 결정하기 위해 Hermes 저장소를 모듈 단위로 분류한다.

이 문서는 *결정의 기준선*이지 *전수 코드 분석*은 아니다. 각 모듈의 정확한 동작은 차용 작업 시점에 해당 모듈만 더 깊게 본다.

## 메타

- 작성일: 2026-05-13
- 기준 커밋: `.hermes-clone/` shallow clone HEAD (2026-05-13)
- 측정 도구: `find` + `wc -l`
- 결정 권한: ax 센터. 본 문서는 초안이며 차용 작업 진행 중 갱신될 수 있다.

---

## 1. 차용 강도 정의

| 강도 | 의미 | 작업 방식 | 라이선스 헤더 |
|------|------|---------|------------|
| **🟢 Vendor copy** | Hermes 코드를 그대로 복사 후 점진 수정. 알고리즘+구현 모두 차용. | `cp <hermes>/<file> sandbox/.../<file>` → MIT 헤더 부착 → import 경로만 수정 | "Adapted from" — 수정 내역은 git log로 추적 |
| **🟡 Port** | 알고리즘은 동일하나 우리 컨벤션으로 재작성. 코드는 새로 작성하되 노하우는 차용. | 원본을 옆에 두고 우리 스타일로 재작성 | "Ported from" — 알고리즘 출처 명시 |
| **🔵 Reference** | 원리만 보고 우리 식으로 새로 작성. 코드 참조 없음. | 원본 docstring/README만 읽고 작성 | 없음 (자체 작성) |
| **🔴 Drop** | 가져오지 않음. | — | — |

## 2. Hermes 저장소 규모 (실측)

`.hermes-clone/` 기준, 코드 파일(.py/.ts/.tsx/.js) 줄 수:

| 디렉터리 | 파일 수 | 라인 수 | 본 프로젝트 관심도 |
|----------|--------|---------|---------------|
| `agent/` | 70 | **41,942** | 🔴 핵심 — 자기진화 루프, memory, prompt builder, curator |
| `tools/` | 102 | 67,248 | 🟡 선별 차용 — 보안 화이트리스트 적용 |
| `skills/` | 44 | 13,259 | 🔵 SKILL.md 컬렉션 (코드가 아니라 컨텐츠) |
| `cron/` | 3 | 2,976 | 🟡 자기진화 트리거 |
| `gateway/` | 61 | 80,768 | 🔴 대부분 Drop, OpenAI API 서버만 차용 |
| `hermes_cli/` | 75 | 85,077 | 🔴 대부분 Drop (CLI/dashboard UX) |
| `providers/` | 2 | 357 | 🟡 LLM provider adapter |
| `plugins/` | 91 | 37,220 | 🔴 Drop (사내 plugin 시스템 우리 표준으로) |
| `acp_adapter/` | 9 | 3,974 | 🔴 Drop |
| `tui_gateway/` | 8 | 7,450 | 🔴 Drop |
| `web/` | 87 | 26,809 | 🔴 Drop (우리는 자체 웹 UI) |
| `ui-tui/` | 305 | 58,104 | 🔴 Drop |
| `website/` | 7 | 2,779 | 🔴 Drop (Hermes 사이트) |
| 루트 `*.py` (16개) | 16 | ~10,000 | 혼합 — 아래 표 참조 |

**총 코드량**: 약 440,000 라인. 본 프로젝트가 실제로 차용할 부분은 이 중 10~15% 추정 (40~60k 라인).

---

## 3. 모듈별 차용 강도 매트릭스

### 3.1 자기진화 핵심 (`agent/`) — 본 프로젝트의 진짜 가치

| 파일/모듈 | 라인 | 역할 | 차용 강도 | 비고 |
|-----------|-----|------|---------|------|
| **`agent/curator.py`** | **1,781** | **Background skill 유지보수 오케스트레이터 — 자기진화의 두뇌. inactivity-triggered.** | **🟢 Vendor copy** | **Phase 0 첫 시범 대상** |
| `agent/skill_commands.py` | 501 | `/skill-name` 슬래시 커맨드 핸들러 (skill 호출 진입점) | 🟡 Port | UI 진입점은 다르지만 핸들러 로직은 동일 |
| `agent/skill_preprocessing.py` | 131 | skill 본문 전처리 (frontmatter 파싱 등) | 🟢 Vendor copy | 작고 명확. 그대로 가져옴 |
| `agent/skill_utils.py` | 511 | skill 관련 유틸 (경로 해석, 메타데이터, 검색) | 🟢 Vendor copy | |
| `agent/memory_manager.py` | 555 | memory 큐레이션 관리자 | 🟢 Vendor copy | 자기진화의 또 다른 핵심 |
| `agent/memory_provider.py` | 279 | memory 백엔드 abstraction | 🟡 Port | 우리 storage layer로 변형 |
| `agent/context_compressor.py` | 1,555 | long context 압축 | 🟢 Vendor copy | LLM 비용 최적화 노하우 |
| `agent/context_engine.py` | — | 컨텍스트 조립 엔진 | 🟢 Vendor copy | 라인 수 미측정, 차용 작업 시 측정 |
| `agent/prompt_builder.py` | — | 시스템 프롬프트 빌더 | 🟢 Vendor copy | 자기진화의 핵심 노하우 (어떤 컨텍스트를 어떻게 넣는가) |
| `agent/prompt_caching.py` | — | Anthropic prompt caching 활용 | 🟢 Vendor copy | LLM 비용 절감 직결 |
| `agent/auxiliary_client.py` | — | curator 등이 쓰는 별도 LLM client | 🟢 Vendor copy | |
| `agent/trajectory.py` | — | 대화 trajectory 관리 | 🟢 Vendor copy | |
| `agent/insights.py` | — | usage insight 추출 | 🟡 Port | 우리 메트릭 시스템에 맞게 |
| `agent/onboarding.py` | — | 신규 사용자 온보딩 | 🔵 Reference | 사내 온보딩 시나리오 다름 |
| `agent/title_generator.py` | — | 세션 자동 title 생성 | 🟢 Vendor copy | 작고 독립적 |
| `agent/error_classifier.py` | — | 에러 분류 | 🟢 Vendor copy | |
| `agent/redact.py` | — | secret/PII redaction | 🟢 Vendor copy | 보안 직결 |
| `agent/tool_guardrails.py` | — | tool 호출 가드레일 | 🟢 Vendor copy | 보안 정책과 결합 필요 |
| `agent/file_safety.py` | — | 파일 접근 안전성 | 🟢 Vendor copy | 보안 정책과 결합 필요 |
| `agent/shell_hooks.py` | — | bash 실행 hook | 🟡 Port | 사내 보안 정책으로 강화 필요 |
| `agent/account_usage.py` | — | 토큰 사용량 추적 | 🟢 Vendor copy | 비용 통제 직결 |
| `agent/credential_pool.py` | — | API 키 풀 | 🟡 Port | 사내 키 관리 표준에 맞게 |
| `agent/usage_pricing.py` | — | 모델별 가격표 | 🟡 Port | 우리 가격 정책 적용 |
| `agent/rate_limit_tracker.py` | — | rate limit 추적 | 🟢 Vendor copy | |
| `agent/retry_utils.py` | — | retry 로직 | 🟢 Vendor copy | |
| `agent/think_scrubber.py` | — | thinking 토큰 정리 | 🟢 Vendor copy | |
| LLM provider adapters (`anthropic_adapter.py`, `bedrock_adapter.py`, `gemini_*.py` 등 12개) | — | provider별 API 변환 | 🟡 Port — 필요한 것만 | 우리는 Claude + 1~2개만. 나머지 Drop |
| `agent/transports/` | — | 모델 호출 전송 계층 | 🟡 Port | |
| `agent/lsp/` | — | LSP 통합 (IDE 통합용) | 🔴 Drop | 본 프로젝트 무관 |
| `agent/i18n.py` | — | 다국어 | 🟡 Port | 한국어 메시지 필요 |
| `agent/copilot_acp_client.py` | — | GitHub Copilot ACP 클라이언트 | 🔴 Drop | |
| `agent/google_*.py`, `agent/credential_sources.py` | — | OAuth/Code Assist 통합 | 🔴 Drop | 사내 SSO로 대체 |
| `agent/insights.py`, `agent/display.py`, `agent/manual_compression_feedback.py`, `agent/subdirectory_hints.py`, `agent/markdown_tables.py`, `agent/curator_backup.py`, `agent/lmstudio_reasoning.py`, `agent/model_metadata.py`, `agent/models_dev.py`, `agent/moonshot_schema.py`, `agent/nous_rate_guard.py`, `agent/plugin_llm.py`, `agent/skill_commands.py`, `agent/image_*` | — | 보조 기능 | 차용 작업 시 모듈별 결정 | |

### 3.2 자기진화 트리거 (`cron/`)

| 파일 | 라인 | 역할 | 차용 강도 |
|------|-----|------|---------|
| `cron/scheduler.py` | 1,820 | 시간 기반 작업 스케줄러 | 🟡 Port — 우리는 더 단순한 스케줄러로 충분할 수 있음 |
| `cron/jobs.py` | 1,114 | 정기 작업 정의 (memory cleanup, skill review 등) | 🟢 Vendor copy — 작업 종류 자체가 자기진화 노하우 |
| `cron/__init__.py` | 42 | — | 🟢 Vendor copy |

### 3.3 루트 단일 파일 (`*.py`)

| 파일 | 라인 | 역할 | 차용 강도 |
|------|-----|------|---------|
| `run_agent.py` | ~15,500 | `AIAgent` 클래스 — 에이전트 메인 루프 | 🟡 Port (분할) — 거대한 단일 파일을 우리는 여러 모듈로 분리 |
| `trajectory_compressor.py` | 1,508 | 대화 trajectory 압축 (LLM 비용 절감) | 🟢 Vendor copy |
| `toolsets.py` + `toolset_distributions.py` | — | tool 그룹 정의 | 🟡 Port |
| `model_tools.py` | — | model-tool 매핑 | 🟡 Port |
| `mcp_serve.py` | 897 | Hermes를 MCP 서버로 노출 | 🔴 Drop |
| `cli.py` | — | 인터랙티브 CLI (`HermesCLI`) | 🔴 Drop |
| `rl_cli.py` | — | 강화학습 CLI | 🔴 Drop |
| `mini_swe_runner.py` | — | SWE-bench runner | 🔴 Drop |
| `batch_runner.py` | — | 배치 실행기 | 🔴 Drop |
| `hermes_bootstrap.py` | — | Windows UTF-8 stdio 설정 | 🟢 Vendor copy (조건부, Windows 지원할 때만) |
| `hermes_constants.py` | 345 | `HERMES_HOME` 등 상수 | 🟡 Port — 이름만 우리 것으로 |
| `hermes_logging.py` | — | 로깅 설정 | 🟡 Port |
| `hermes_state.py` | — | 글로벌 상태 | 🟡 Port |
| `hermes_time.py` | — | 시간 유틸 | 🟢 Vendor copy |
| `utils.py` | — | 잡다 유틸 | 🟢 Vendor copy |

### 3.4 Tool 시스템 (`tools/`)

102개 파일, 67k 라인. 거의 모든 tool이 여기.

| 카테고리 | 차용 강도 | 비고 |
|---------|---------|------|
| 코어 tool (terminal, file ops, web search, http_get 등) | 🟡 Port — **사내 보안 화이트리스트** | Hermes의 위험 tool(임의 bash) 그대로 차용 시 사내 보안팀 통과 못함 |
| MCP tool 통합 (`tools/mcp_tool.py` 등) | 🟡 Port | 사내 MCP 서버 화이트리스트 적용 |
| 외부 SaaS 통합 (GitHub, Notion, Slack 등) | 🟡 선별 Port | 필요한 것만 |
| 이미지/오디오/비디오 생성 tool | 🔴 Drop (Phase 1) → Phase 3 재검토 | 본 프로젝트 초기 범위 외 |
| `tools/lazy_deps.py` | 🟢 Vendor copy | 선택적 의존성 관리 |

차용 작업은 **tool 단위로** 진행한다 (1 tool = 1 작업). 첫 Phase는 terminal, file ops 정도만.

### 3.5 Skill 컨텐츠 (`skills/`)

44개 폴더, 각 폴더 = 하나의 도메인 SKILL.md 모음.

- **🔵 Reference** — 컨텐츠는 사내 도메인이 다르므로 그대로 가져오지 않음. **SKILL.md 작성 형식**(frontmatter, 본문 구조)만 차용.
- 단, **`skills/autonomous-ai-agents/`, `skills/software-development/`, `skills/red-teaming/`** 일부는 사내에서도 유용할 수 있음 → Phase 4 사내 표준 라이브러리에 선별 import.

### 3.6 Gateway (`gateway/`) — 대부분 Drop

| 모듈 | 차용 강도 | 비고 |
|------|---------|------|
| `gateway/platforms/api_server.py` | 🔵 Reference | OpenAI 호환 API 서버 — 단순 aiohttp wrapper. 우리가 직접 짜는 게 깔끔 |
| `gateway/platforms/webhook.py` | 🔴 Drop | Phase 4 이후 재검토 |
| `gateway/platforms/{telegram,discord,slack,whatsapp,signal,...}.py` | 🔴 Drop | 본 프로젝트 명시적 제외 |
| `gateway/run.py`, `gateway/delivery.py`, `gateway/session.py` | 🔴 Drop | Hermes의 메신저 라우팅 모델은 우리와 다름 |
| `gateway/builtin_hooks/` | 🔴 Drop | |

### 3.7 기타 — 모두 Drop

- `hermes_cli/` (CLI/dashboard) — 우리는 웹 UI
- `acp_adapter/`, `tui_gateway/` — 우리 진입점 아님
- `web/`, `ui-tui/` — 우리 웹 UI 자체 제작
- `plugins/` — 우리 plugin 표준 (있다면) 별도 설계
- `website/` — Hermes 자체 사이트
- `tests/` — 차용 시 함께 가져오는 테스트만 (모듈별)

---

## 4. Drop 리스트 (가져오지 않는 것 명시)

다음은 **명시적으로 가져오지 않는다**. 이후 차용 작업 중 "혹시 이건?" 같은 결정 비용을 줄이기 위해.

- 모든 메신저 platform adapter (Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Email, Google Chat, Teams, DingTalk, 등)
- CLI 인터랙티브 UX (TUI, prompt_toolkit 통합, 슬래시 커맨드 자동완성)
- Web dashboard (`hermes_cli/web_server.py`)
- ACP / MCP serve (외부 진입점)
- 6 terminal backend (Docker/SSH/Daytona/Singularity/Modal — 우리는 Docker만)
- profile 시스템 (`~/.hermes/profiles/`)
- RL/atropos/datagen 관련 (`rl_cli.py`, `tinker-atropos/`, `datagen-config-examples/`)
- SWE-bench runner
- 다양한 LLM provider 중 우리가 안 쓸 것 (Bedrock, Gemini Cloudcode, LMStudio, Moonshot, Xiaomi MiMo 등 — 우리는 Claude API + 1개)
- LSP 통합
- 이미지/오디오/비디오 생성 tool (Phase 1 기준. Phase 3 재검토)
- Hermes 자체 marketing 사이트 (`website/`)

---

## 5. 의존성 그래프 — 1차

`agent/curator.py`를 떼어내려면 무엇이 필요한가? (Phase 0 첫 시범 대상)

```
agent/curator.py
├─→ agent/auxiliary_client.py    (별도 LLM client)
├─→ agent/skill_utils.py         (skill 경로/메타데이터)
├─→ agent/skill_preprocessing.py (frontmatter 파싱)
├─→ agent/prompt_builder.py      (curator용 시스템 프롬프트)
├─→ agent/account_usage.py       (토큰 사용량 기록)
├─→ agent/redact.py              (PII 제거)
├─→ hermes_constants.py          (HERMES_HOME 등)
├─→ hermes_logging.py
├─→ utils.py
└─→ run_agent.py 의 일부         (LLM 호출 wrapper)
```

위 의존성 그래프는 **추정**이다. Phase 0의 `research/skill-loop-port-feasibility.md` 작성 단계에서 실제 import 그래프를 측정해서 갱신한다.

추정이 맞다면 첫 시범에 필요한 코드량은 약 **5,000~7,000 라인**. 이 정도는 1주일 안에 떼어낼 수 있는 규모.

---

## 6. 차용 우선순위 (Phase 1+ 작업 순서 초안)

Phase 0 게이트 통과 후 Phase 1 작업 순서 제안:

1. **메시지 처리 루프** (`run_agent.py` 분할 Port) — 엔진의 척추
2. **LLM provider adapter** (Anthropic만) — 호출 인터페이스
3. **prompt builder + caching** (Vendor copy) — 컨텍스트 조립
4. **trajectory + context compressor** (Vendor copy) — 컨텍스트 관리
5. **memory manager** (Vendor copy) — 영속 메모리
6. **skill utils + preprocessing** (Vendor copy) — skill 로딩
7. **skill 자동 생성 (curator)** — Phase 0에서 이미 시범 완료 → engine/으로 승격
8. **tool 시스템 (terminal + file ops만)** Port — 보안 화이트리스트
9. **session search (FTS5)** Port
10. **OpenAI 호환 API 서버** Reference로 자체 작성
11. **자동 git commit + snapshot** Port

각 단계는 Phase 1 안에서 독립 PR 단위.

---

## 7. 본 문서의 갱신 정책

- 차용 작업 진행 중 새로 측정한 사실은 본 문서에 반영한다.
- 모듈별 차용 강도가 작업 도중 바뀌면 변경 이력에 기록한다.
- Phase 게이트 시점에 전체 매트릭스를 재검토한다.

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-13 | 초안 작성. 옵션 C 결정 직후. 라인 수는 실측, 차용 강도는 *제안* (Phase 0 시범 결과로 검증 예정) |
