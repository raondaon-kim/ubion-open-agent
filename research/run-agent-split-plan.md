# `run_agent.py` 분할 계획 — 단위 3-0

> Phase 1 단위 3 (메시지 처리 루프 Port) 의 사전 설계. `.hermes-clone/run_agent.py` (14,553 라인) 을 우리 트리(`engine/`)로 어떻게 쪼개 옮길지 정한다.

## 메타

- 대상 파일: `.hermes-clone/run_agent.py` @ `b06e9993021a8eebd891fc60d52372446315b2f0`
- 라인 수: **14,553** (모듈 헤더 + `AIAgent` 한 클래스 + `main()`)
- 클래스 `AIAgent` 라인 범위: **1094 ~ 15536** (약 14,442 라인, 193개 메서드 중 178개)
- 단위 2에서 이미 가져온 부분: `IterationBudget` (Port, `engine/core/budget.py`), `AIAgent` 골격 ~354 라인 (Port, `engine/core/agent.py`)
- 작성일: 2026-05-13

## 원칙

1. **단위 2의 `engine/core/agent.py` 가 본체로 남는다** — `run_agent.py` 를 통째로 옮기지 않는다. 우리 모델이 필요로 하는 메서드만 골라 흡수.
2. **카테고리별로 별도 파일** — `AIAgent` 라는 14k 라인 클래스를 `engine/core/agent.py` 단일 파일로 유지하지 않는다. mixin 또는 helper 함수 분리.
3. **Hermes 다중 provider 분기는 대부분 Drop** — Phase 1 Anthropic 단일. OpenAI/Codex/Qwen/Copilot/Ollama/LMStudio 분기는 가져오지 않음.
4. **3개 강도 태깅** — Vendor copy (Hermes 라이선스 헤더 + 0행 변경) / Port (구조 변경) / Drop (가져오지 않음).
5. **단계적 Port** — 단위 3 끝에 14k 라인을 다 옮기지 않는다. *시 에이전트 시나리오에 꼭 필요한 메서드만* 단위 3 범위로 흡수. 나머지는 Phase 1 후속 단위 또는 Phase 2.

## 카테고리 그루핑 (29개)

라인 수 = 다음 메서드 시작 - 현재 메서드 시작. `AIAgent` 클래스 내 178개 메서드를 의미상 그루핑.

| # | 카테고리 | 라인 범위 | 라인 수 | 메서드 수 | Phase 1 강도 | 우리 모듈 |
|---|----------|-----------|---------|-----------|--------------|-----------|
| C01 | 모듈 상단 helpers | 1~1093 | 1,093 | 24 fn + 4 cls | 부분 Port | `engine/core/sanitize.py` + 기존 `engine/core/budget.py` |
| C02 | `AIAgent.__init__` + base_url 프로퍼티 | 1094~2484 | 1,391 | 3 | **Port (선별)** | `engine/core/agent.py` 확장 |
| C03 | 세션 DB / state reset | 2485~2597 | 113 | 3 | Port | `engine/core/session_state.py` |
| C04 | LMStudio/switch_model 등 다중 provider | 2598~2791 | 194 | 2 | **Drop** | — |
| C05 | print/vprint/quiet/status/warning | 2792~2923 | 132 | 5 | Port (얇게) | `engine/core/log.py` |
| C06 | stream diagnostics | 2924~3150 | 227 | 5 | **Drop** (Phase 2 streaming 시점에) | — |
| C07 | auxiliary failure / runtime info | 3151~3171 | 21 | 2 | Drop | — |
| C08 | compression model feasibility | 3172~3358 | 187 | 2 | Drop (단위 5에서) | — |
| C09 | URL flavor 판별 (openai/azure/copilot/openrouter) | 3359~3456 | 98 | 5 | **Drop** (Anthropic 단일) | — |
| C10 | API call timeout / stale timeout | 3457~3597 | 141 | 5 | Port | `engine/core/timeouts.py` |
| C11 | Responses API / max_tokens 등 model capability | 3598~3852 | 255 | 8 | **Drop** | — |
| C12 | reasoning content extraction | 3853~3932 | 80 | 1 | Drop (Anthropic은 thinking 별도 처리) | — |
| C13 | task / background review / memory metadata | 3933~4399 | 467 | 5 | **부분 Port** (background review = curator 호환용만) | `engine/core/background_review.py` |
| C14 | message sequence 정리 (persist/repair/flush) | 4400~4677 | 278 | 6 | Port | `engine/core/messages.py` |
| C15 | trajectory 변환/저장 | 4678~4901 | 224 | 2 | Vendor copy (단위 5에서) | `engine/storage/trajectory.py` |
| C16 | API error 분류/마스킹/context 추출 | 4902~5099 | 198 | 4 | Vendor copy | `engine/core/api_errors.py` |
| C17 | session log 저장 / dump api request | 5000~5173 | 174 | 3 | Port | `engine/storage/session_log.py` |
| C18 | interrupt / steer / 사용자 입력 | 5174~5326 | 153 | 4 | Port | `engine/core/control.py` |
| C19 | file mutation 검증 | 5327~5486 | 160 | 4 | **Drop (단위 8에서 재검토)** | — |
| C20 | activity / rate limit / cache status | 5487~5554 | 68 | 5 | Port (얇게) | `engine/core/metrics.py` |
| C21 | memory provider lifecycle | 5555~5702 | 148 | 3 | Port (단위 6에서) | `engine/core/memory_lifecycle.py` |
| C22 | client release / close / todo hydrate | 5703~5804 | 102 | 3 | Port | `engine/core/agent.py` (확장) |
| C23 | system prompt builder | 5805~6036 | 232 | 2 | **Vendor copy (단위 4)** | `engine/core/prompt_builder_glue.py` |
| C24 | tool call id / sanitize / dedupe / cap | 6037~6404 | 368 | 9 | Port | `engine/core/tool_call_utils.py` |
| C25 | OpenAI client lifecycle (대량) | 6405~6841 | 437 | 14 | **Drop 전부** | — |
| C26 | Codex stream + credential refresh + 6개 provider | 6842~7390 | 549 | 8 | **Drop 전부** | — |
| C27 | API call core (interruptible / streaming) | 7392~7709 | 318 | 8 | **Port (선별)** | `engine/core/api_call.py` |
| C28 | streaming API call 본체 (거대) | 7710~8602 | 893 | 1 | Drop (Phase 1 non-streaming) | — |
| C29 | fallback activation / primary recovery | 8603~9001 | 399 | 3 | Drop (Phase 1 Anthropic 단일) | — |
| C30 | vision/image 처리 | 9002~9344 | 343 | 7 | Drop (Phase 1 텍스트 only) | — |
| C31 | Anthropic prep / Qwen prep | 9345~9443 | 99 | 4 | **부분 Port** (Anthropic prep 만) | `engine/llm/anthropic.py` 확장 |
| C32 | `_build_api_kwargs` | 9444~9659 | 216 | 1 | Port | `engine/core/api_kwargs.py` |
| C33 | reasoning extra_body / LMStudio reasoning | 9660~9781 | 122 | 4 | Drop | — |
| C34 | `_build_assistant_message` | 9782~9974 | 193 | 1 | Port | `engine/core/api_kwargs.py` |
| C35 | thinking pad / Kimi / DeepSeek 트윅 | 9975~10086 | 112 | 4 | Drop | — |
| C36 | tool call 인자 sanitize (strict API) | 10087~10236 | 150 | 3 | Port | `engine/core/tool_call_utils.py` 확장 |
| C37 | `_compress_context` | 10237~10414 | 178 | 1 | Vendor copy (단위 5) | `engine/storage/compress.py` |
| C38 | tool guardrail | 10415~10452 | 38 | 4 | **Drop (Phase 1 보안팀 없음)** | — |
| C39 | tool dispatch — `_execute_tool_calls` 진입점 | 10453~10495 | 43 | 2 | **Port (핵심)** | `engine/core/tool_dispatch.py` |
| C40 | `_invoke_tool` (개별 tool 호출) | 10495~10606 | 112 | 2 | **Port (핵심)** | `engine/core/tool_dispatch.py` |
| C41 | concurrent tool execution | 10607~11018 | 412 | 1 | Drop (Phase 1 순차) | — |
| C42 | sequential tool execution | 11019~11463 | 445 | 1 | **Port (강도 하향)** — Hermes의 OpenAI ToolCall 형태/guardrail/checkpoint/activity_callback 다중 의존이 우리 Anthropic 단일 환경과 충돌. 의미 (interrupt skip, JSON arg 안전 파싱, error 형태) 만 보존, 골격 재작성. | `engine/core/tool_dispatch.py` |

### 단위 10 프레임워크 결정 (사용자 2026-05-13)

원래 분할 계획: "aiohttp wrapper". 실제 구현 시점에 FastAPI + uvicorn 로 변경. 사유:
- FastAPI 는 OpenAPI 자동 생성 + pydantic 검증 + 표준 async 친화
- TestClient 가 내장되어 단위 테스트가 깔끔
- Phase 2/3 의 SSO/멀티유저/dashboard 확장이 자연

aiohttp 도 가능하지만 SSE 구현이 더 수동적. 이 단위는 Reference 강도라 프레임워크 자체에 큰 의미 없음.
| C43 | `_handle_max_iterations` | 11464~11678 | 215 | 1 | Port | `engine/core/agent.py` (확장) |
| C44 | **`run_conversation` 메인 루프 (거대)** | 11679~15536 | **3,858** | 1 | **Port (핵심, 단계 분할)** | `engine/core/agent.py` 본체 |
| C45 | `chat` 래퍼 | 15537~15551 | 15 | 1 | Port | `engine/core/agent.py` (확장) |

총: **14,442 라인**.

## Phase 1 단위 3 범위 (가져올 카테고리)

다음 카테고리만 단위 3 범위에서 흡수한다 (**우선순위 순**):

1. **C44 `run_conversation`** — 단위 3 의 핵심. 분할 Port (아래 3-1 ~ 3-4 참고).
2. **C39, C40, C42** tool dispatch — `run_conversation` 이 호출하는 즉시 의존. 함께 가져옴.
3. **C24, C36** tool call utils — 위 dispatch가 의존.
4. **C14** messages 정리 — `run_conversation` 이 의존.
5. **C16** API error 분류 — 우리 `engine/core/errors.py` 가 이미 Vendor copy. 누락 분만 보강.
6. **C18** interrupt/steer — Phase 1 CLI 에서 Ctrl+C 등 처리.
7. **C22** close/release — Phase 1 graceful shutdown.
8. **C32, C34, C31** api_kwargs + Anthropic prep — `_call_llm_with_retry` 가 의존.
9. **C43** max_iterations 처리 — `run_conversation` 의 정상 종료 경로.
10. **C27** API call 진입 — `_interruptible_api_call` 의 Anthropic 분기만.

미루는 것 (Phase 1 후속 또는 Phase 2):

- C04, C06~C13, C19, C25, C26, C28~C30, C33, C35, C38, C41 — 위 표에서 **Drop** 으로 마킹.
- C03 reset_session_state — Phase 1 끝나면 별 의미 없음.
- C05 print/vprint — `engine/core/log.py` 얇게 Port.
- C15 trajectory — 단위 5.
- C17 session log 저장 — 단위 5 또는 9.
- C20 metrics — Phase 2.
- C21 memory lifecycle — 단위 6.
- C23 system prompt builder — 단위 4.
- C37 compress — 단위 5.

## 단위 3 sub-task 분할

`run_conversation` (C44, 3,858 라인) 자체를 한 번에 옮기지 않는다. 4단계로 쪼갠다.

### 단위 3-1 — Pre-turn setup + Post-turn teardown

- `_install_safe_stdio`, `_ensure_db_session`, `_sanitize_surrogates` 호출 묶음
- 라인 11707~11900 부근 (개략)
- task_id 생성, retry 카운터 reset, vision flag reset
- 출력: `engine/core/turn_setup.py` (Port)
- 검증: `run_conversation()` 진입 직후 ~ 메인 while 직전까지 ASCII transcript 출력 일치

### 단위 3-2 — 메인 while 루프 + LLM 호출 dispatch

- 라인 ~12100 부근 부터 메인 루프 진입
- 우리 단위 2 의 `_run_loop` 가 이미 *최소형* 으로 구현됨. 이걸 확장:
  - context compression trigger (단위 5에서 활성화)
  - `_persist_session` 호출 위치
  - `_save_trajectory` 호출 위치
  - sub-iteration retry (invalid_tool, invalid_json, empty_content 등)
- 출력: `engine/core/agent.py` 의 `_run_loop` 확장
- 검증: curator end-to-end 동등 + 1차 retry 시나리오 1개 통과

### 단위 3-3 — Tool dispatch sequential

- C39+C40+C42 의 *의미* 를 Port. Vendor copy 불가 — Anthropic 환경/dataclass ToolCall/tool_result block 차이가 큼
- 우리 단위 2 `_execute_tool_calls` (간이형) 폐기, Port 로 교체
- 보존할 의미:
  - 각 tool 호출 직전 interrupt 체크 → 남은 호출 전부 skip 처리, skip 결과 block 도 transcript 에 기록 (Anthropic 은 모든 `tool_use` id 에 대응하는 `tool_result` 가 필요)
  - JSON 인자 안전 파싱 (이미 dict 인 경우 통과, str 이면 json.loads, 실패 시 빈 dict)
  - tool 핸들러 예외 catch → error 형태 tool_result 반환 (`is_error=True`)
  - tool 결과 stringify (현재 `_stringify_tool_value` 이미 단위 2 에서 구현)
- 미루는 것 (Vendor copy 시도조차 안 함):
  - guardrail (Phase 3, 단위 8 화이트리스트로 대체)
  - plugin hooks (단위 8 또는 Phase 2)
  - checkpoint_mgr (단위 11 git auto-commit)
  - activity_callback / inactivity monitor (Phase 2 gateway)
  - todo/memory/clarify/delegate/session_search 의 inline 처리 (단위 6/8/9 에서 우리 tool 레지스트리로)
- 출력: `engine/core/tool_dispatch.py` (Port)
- 검증: 단위 테스트 — interrupt skip, JSON 파싱 실패, tool 예외, str/dict 인자 모두 통과

### 단위 3-4 — Streaming callback 처리

- 단위 3 범위에 *포함 안 함* (Phase 2 또는 단위 10에서)
- 단위 3 끝 시점에 `stream_callback` 인자는 **무시** (warning 로그만)
- 이유: 단위 10 (OpenAI 호환 API 서버) 시점에 SSE 와 함께 처리하는 게 자연스러움

## 검증 기준 (단위 3 종료)

- [ ] `engine/core/agent.py` 의 `run_conversation` 이 Hermes `run_agent.py:run_conversation` 의 **non-streaming, non-vision, Anthropic-only** 경로와 동등 동작
- [ ] curator (`engine/learning/curator.py`) 가 우리 `AIAgent` 로 end-to-end 재실행 시, 단위 2 smoke test 와 동등 (REPORT.md 생성, 클러스터 식별)
- [ ] sub-iteration retry (invalid_tool_retries) 1개 시나리오 통과
- [ ] graceful interrupt (Ctrl+C 또는 `.interrupt()`) 정상 처리
- [ ] `engine/NOTICE.md` 에 C39/C40/C42 Vendor copy 항목 추가

## 미루는 것 — 명시적 항목

다음은 단위 3에서 *명시적으로* 가져오지 않는다. 향후 누군가 "왜 안 했지?" 의문 방지용 기록:

1. **다중 provider 분기** (C04, C09, C11, C25~C26, C29, C33, C35) — Phase 1 = Anthropic 단일. Phase 2에서 OpenAI 추가 시 재검토. 약 2,800 라인 절약.
2. **streaming API call** (C28, 893 라인) — Phase 1 non-streaming. 단위 10 (API 서버) 와 함께 가져옴.
3. **vision/image** (C30, 343 라인) — Phase 1 텍스트 전용 (시 에이전트 시나리오).
4. **concurrent tool execution** (C41, 412 라인) — Phase 1 순차 실행. 부작용 적고 디버깅 쉬움. Phase 2 성능 작업에서 검토.
5. **tool guardrail** (C38) — Phase 1 보안팀 게이트 미적용. 단위 8 화이트리스트로 대체.
6. **fallback / credential pool** (C29, C26) — Phase 1 단일 API key. 다중 키 풀은 Phase 3.

## 라인 절감 추정

| 분류 | 라인 |
|------|------|
| 단위 3 범위 (Vendor copy + Port) | ~5,500 |
| 단위 4~9 흡수 예정 | ~3,000 |
| Phase 2 이상으로 미룸 | ~3,500 |
| **Drop (영구 미흡수)** | **~2,500** |

총 14,442 라인 중 약 17% Drop. Phase 0 차용 시범의 85% 흡수율과 일관.

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-13 | 초안. 단위 3-0 산출물 |
