# Phase 1 TODO — 자체 엔진 프로토타입 (옵션 C)

> v0.1에서는 "2인 PoC, docker-compose, dispatcher + 웹 UI" 계획이었음. v0.2 옵션 C 결정 후 의제 전면 변경. PROJECT_SPEC v0.2~v0.3 §2.2 / §4 / §9 참조.

## 목적

Hermes 코드를 본 트리(`engine/`)로 흡수하여 **자체 엔진**으로 메시지 → LLM → tool → 자기진화 루프가 end-to-end 동작하는 프로토타입을 만든다.

ax 센터 로컬 1대에서 1인 동작 검증까지가 본 Phase의 범위. 멀티유저/컨테이너/SSO/보안팀은 Phase 3.

## Phase 1 종료 기준 (PROJECT_SPEC v0.3 §9, 2026-05-13 보강)

**(A) 기술 완성도** — 본 문서의 단위들 모두 종료
- 단위 1~10 ✅ 완료 (2026-05-13)
- 단위 11 ⏸ 보류 (Phase 1 (B) 회고 후 결정)
- 단위 12 (자체 웹앱 UI) — Phase 1 (B) 진입 전 필수 (사용자 결정 2026-05-13)
- 단위 13 (DeepSeek 다중 provider) — Phase 1 (B) 진입 전 필수 (사용자 결정 2026-05-13)

**(B) Goal 검증** — 시 에이전트 시나리오 1주 사용으로 자기진화 가치 확인 (`research/phase-1-demo-scenario-poet.md`)

순서: 단위 13 → 단위 12 → Phase 1 (B) 진입. (A) 의 모든 항목 (단위 11 제외) 통과 후 (B). 둘 다 통과해야 Phase 2 진입.

## 단위 우선순위 정책

**기술 의존성 순서** (옵션 나, 2026-05-13 결정). Goal-driven 재배치(옵션 가)는 *기각* — 다음 이유:
- 단위 3 (`run_agent.py` 분할)은 단위 4 prompt builder가 의지하는 자리가 많아 미루기 어려움
- 단위 4 → 6 → 8 묶음으로 Goal 검증을 빨리 가는 게 매력적이지만, 도중에 단위 3을 안 한 채로는 안정성 부족
- 11단위 다 끝낸 뒤 시 에이전트 1주 사용으로 Goal 검증하는 게 SPEC v0.3 §9 (A)+(B) 순차와 일치

### 단위 4 재배치 (2026-05-13)

단위 3 종료 시점에 prompt_builder.py (1298 라인) 의 의존성을 실측한 결과, `build_skills_system_prompt` 가 skill_utils 의 5개 함수 + agent_home 의 `get_all_skills_dirs/get_disabled_skill_names` + memory_provider 의 prefetch 에 *깊게* 묶임. 사용자 요구(*"대충 물어봐도 정확히 답하고 메모리와 연동"*, *"메모리가 없어도 에러는 없어야 함"*) 의 핵심이 prompt_builder 의 적극 차용에 있어, 단위 4 를 간소 Port 로 좁히는 대신 의존을 *먼저 채우는* 순서로 재배치:

**원래 순서**: 4 (prompt) → 5 (trajectory) → 6 (memory) → 7 (skill utils) → 8~11
**새 순서**: **5 → 6 → 7 → 4 (prompt builder 통째 Vendor copy)** → 8~11 (사용자 결정 옵션 Ⅱ, 2026-05-13)

단위 4 만 뒤로 밀림. 1298 라인 0-line modification Vendor copy 가능. Phase 1 (B) 시 에이전트 검증은 11단위 *전부* 완료 후라 (B) 진입 시점은 불변.

## 전제

- 엔진 전략: 옵션 C (PROJECT_SPEC §2.2)
- 언어: Python
- Hermes 차용 기준 커밋: `b06e9993021a8eebd891fc60d52372446315b2f0`
- 업스트림 추적: 안 함
- 시간 제약: 없음. 프로토타입 우선
- 사용자: ax 센터 1인 (로컬). 보안팀 게이트 비활성

## 진입 조건

- [x] Phase 0 retrospective에서 Green 판정
- [x] 차용 시범 코드(`sandbox/skill-loop-port/`)가 end-to-end 동작
- [x] 라이선스 정책 (`research/hermes-license-policy.md`)
- [x] 모듈 차용 강도 매트릭스 (`research/hermes-code-walkthrough.md`)
- [ ] `.phase` 파일을 `1`로 전환

## 작업 위치

- 본 트리: `engine/` (Phase 1에서 생성)
- 차용 시범 sandbox: `sandbox/skill-loop-port/` — Phase 1.1 작업에서 승격 후 정리

## 핵심 결정 (Phase 1 시작 시 확정)

- [ ] LLM provider 정책: Anthropic 단일? 추후 OpenAI/로컬 추가?
- [ ] Tool 화이트리스트 초기 범위: terminal + file ops만? web fetch도?
- [ ] Memory 영속 위치 이름: `~/.ubion-agent/` 확정
- [ ] git auto-commit 트리거: 매 trajectory? N분 idle?

---

## 단위 1 — sandbox → engine 승격 ✅ 완료 (2026-05-13)

목적: Phase 0 시범 코드를 본 트리로 옮기고, sandbox의 mock/glue를 본격 구현으로 교체할 준비를 마친다.

**결과**: sandbox의 vendored 3개 파일 + fixtures가 `engine/`으로 이동. shim 파일들은 본 트리에서 import 경로 직접 수정으로 흡수. sandbox는 "승격됨" 표시로 보존.

- [ ] `engine/` 디렉터리 구조 시드
  - `engine/__init__.py`
  - `engine/learning/` (curator)
  - `engine/skills/` (skill_usage, preprocessing 등)
  - `engine/core/` (agent loop, prompt builder)
  - `engine/storage/` (agent_home, memory)
  - `engine/llm/` (provider adapters)
  - `engine/tools/` (terminal, file ops)
  - `NOTICE.md` 루트 레벨로 이동/확장
- [ ] `sandbox/skill-loop-port/curator.py` → `engine/learning/curator.py`
- [ ] `sandbox/skill-loop-port/skill_usage.py` → `engine/skills/usage.py`
- [ ] `sandbox/skill-loop-port/agent_home.py` → `engine/storage/agent_home.py`
- [ ] sandbox shim들은 `engine/` 모듈 구조에 흡수 (별도 shim 파일 필요 없게)
  - `from hermes_constants` → `from engine.storage.agent_home`로 차용 시점 단발 수정
  - `from tools import skill_usage` → `from engine.skills import usage`
- [ ] fixtures는 `tests/fixtures/skills/`로 이동
- [ ] sandbox 디렉터리 폐기 (또는 README에 "승격됨" 표시 + 코드 삭제)

검증:
- [ ] 승격된 `engine/learning/curator.py`가 mock_agent 대신 진짜 agent로 동작 가능 상태 (단위 2 완료 후 검증)

## 단위 2 — AIAgent 코어 + Mock 폐기 ✅ 완료 (2026-05-13)

목적: Mock AIAgent 폐기 + 메시지 루프, 재시도, 에러 분류, IterationBudget, skill_view tool까지 *최소 동작* 셋 구성.

원래 단위 2 범위(Anthropic adapter Port)에서 확장된 이유: 검토 1+2 결과로 단위 2 = "최소 동작 Agent 코어"로 재정의됨. 8개 작업으로 분해:

- [x] **2-1** `engine/core/budget.py` — IterationBudget Port (`run_agent.py:283-325`)
- [x] **2-2** `engine/core/errors.py` — classify_api_error Vendor copy (`agent/error_classifier.py`)
- [x] **2-3** `engine/core/retry.py` — jittered_backoff Vendor copy (`agent/retry_utils.py`)
- [x] **2-4** `engine/llm/anthropic.py` — 얇은 Anthropic adapter 자체 작성 (Reference, ~156 라인. 전체 `agent/anthropic_adapter.py` 2079라인 차용은 추후 단위로 미룸)
- [x] **2-5** `engine/core/agent.py` — AIAgent 골격 Port (`run_conversation` 메인 루프 + tool dispatch + retry)
- [x] **2-6** `engine/skills/utils.py` + `preprocessing.py` Vendor copy
- [x] **2-7** `engine/tools/skill_view.py` 자체 작성 (Reference. progressive disclosure tool)
- [x] **2-8** end-to-end 검증: `engine.core.agent.AIAgent`로 curator 재실행 → sandbox와 동등한 출력 (19초, 클러스터 정확 식별, REPORT.md 생성)

**결과**: Mock AIAgent 폐기. 차용 비율 80%. `engine/NOTICE.md` 일괄 정리.

**의도적으로 미룬 것** (단위 2 범위 밖):
- Delegate tool — 단위 8 (tool 시스템)
- Gateway 세션 캐시 (LRU + TTL) — 단위 10 (API 서버)
- Skill nudge 시스템 — 단위 4 (prompt builder)
- Skill slash-command — 단위 10 또는 Phase 2
- Skill 인라인 shell — 영구 비활성

## 단위 3 — 메시지 처리 루프 Port

차용 대상: `.hermes-clone/run_agent.py` (14,553 라인). 분할 Port.

- [x] **3-0** 분할 계획 작성 — `research/run-agent-split-plan.md` (2026-05-13)
- [x] **3-1** Pre-turn setup → `engine/core/turn_setup.py` (Port, 2026-05-13). Subset: user_message sanitize, task_id 발급, per-turn budget reset, conversation_history hydrate, user_turn_count 카운터, interrupt thread bind. 검증: smoke test 23s, 클러스터 정확 식별, REPORT.md 생성.
- [x] **3-2** 메인 while 루프 정교화 + 단위 테스트 (Port, 2026-05-13). exit_reason 5종 정확 매핑 (`completed`/`interrupted_by_user`/`budget_exhausted`/`max_iterations`/`all_retries_exhausted`), 3개 interrupt checkpoint, 외부 주입 budget 공유 의미 보존 (`_budget_externally_supplied` flag). `tests/unit/test_agent_loop.py` 11/11 green, 5.2s.
- [x] **3-3** Tool dispatch sequential → `engine/core/tool_dispatch.py` (Port, 2026-05-13). 강도 Vendor copy → Port 하향 이유: Hermes 가 OpenAI ToolCall 형태 + guardrail/checkpoint/activity_callback 다중 의존이라 Anthropic dataclass 환경과 충돌. 의미 보존: cooperative interrupt skip, JSON-arg safety, error block shape. 단위 2 `_execute_tool_calls` 폐기. `tests/unit/test_tool_dispatch.py` 8/8 green (총 19/19 5.1s). smoke test 21s.
- [x] `engine/NOTICE.md` 업데이트
- [ ] 통합 검증: invalid_tool_retries 1개 시나리오 (추후 단위 또는 단위 3 마무리에서)

**미루는 것 (단위 3 범위 밖)**: streaming callback (단위 10), 다중 provider (Phase 2), vision (Phase 2), concurrent tool exec (Phase 2), tool guardrail (단위 8 화이트리스트로 대체). 상세는 `run-agent-split-plan.md` 참고.

## 단위 4 — prompt builder + caching Vendor copy ✅ 완료 (2026-05-13)

**재배치 적용**: 단위 5 → 6 → 7 → 4 순서대로 들어옴. prompt_builder.py 의 모든 의존이 자리잡힘.

차용 결과:

- [x] `engine/core/prompt_caching.py` — Vendor copy (59라인, 0-line modification)
- [x] `engine/core/prompt_builder.py` — Vendor copy (1298라인, top-level import 3줄만 engine.* 로 변경; 6개 lazy import 는 try/except 가드되어 무변경)
- [x] `engine/storage/atomic.py` — Port (atomic_json_write 외 3개 helper, 110라인)
- [x] `engine/storage/agent_home.py` 에 `is_wsl()` 추가
- [x] AIAgent.__init__ 에서 `system_prompt` 미주입 시 `_auto_build_system_prompt=True` 플래그. `_call_llm_with_retry` 진입 시 `_build_system_prompt()` lazy 발동. 결과는 캐시됨 (Anthropic prefix-cache 친화)
- [x] `_build_system_prompt()` = skills 인덱스 + context files (SOUL.md/HERMES.md/AGENTS.md/CLAUDE.md/.cursorrules) + memory_manager.build_system_prompt() 조합
- [x] `_invalidate_system_prompt()` — context compression 시 리빌드 트리거
- [x] **invariant #1 검증**: 메모리/SOUL/USER 없어도 prompt builder 가 빈 문자열 반환, 에러 없음. 단위 테스트 5개로 보장
- [x] **invariant #2 검증**: memory provider 의 `system_prompt_block()` 이 *composed system prompt 에 합쳐짐* 단위 테스트로 보장 (`test_memory_block_included_in_composed_prompt`)
- [x] `tests/unit/test_prompt_builder.py` — 13개 단위 테스트
- [x] 전체 64/64 단위 테스트 green @ 15.8s
- [x] curator smoke test 회귀 검증

## 단위 5 — trajectory + context compressor Vendor copy ✅ 완료 (2026-05-13)

**실측 후 범위 조정 (옵션 B-2 사용자 결정)**: trajectory_compressor.py 1,467라인은 batch learning CLI 도구로 Phase 1 무관 — Drop. trajectory.py + context_compressor.py 의존 분석 결과 4개 의존 모듈 추가 차용 필요 (auxiliary_client 4179, context_engine 160, model_metadata 1574, redact 341). auxiliary_client 통째 Vendor copy 는 우리 Anthropic 단일 정책과 충돌 → call_llm 어댑터 (~160라인) 로 대체. model_metadata 는 Anthropic 단일 catalog 로 Port. 나머지는 Vendor copy.

차용 결과:

- [x] `engine/storage/trajectory.py` — Vendor copy (44라인, 0-line modification)
- [x] `engine/learning/context_engine.py` — Vendor copy (207라인, 0-line modification)
- [x] `engine/learning/context_compressor.py` — Vendor copy (1358라인, import 4줄만 engine.* 로 변경)
- [x] `engine/learning/redact.py` — Vendor copy (341라인, 0-line modification)
- [x] `engine/learning/model_metadata.py` — Port (~180라인 vs upstream 1574)
- [x] `engine/llm/aux_client.py` — auxiliary_client 어댑터 (~160라인 vs upstream 4179). `aux` 가 Windows DOS 예약어라 `aux_client` 로 명명
- [x] `engine/core/agent.py` — `_ensure_compressor()` lazy + `_compress_context()` 메서드 + `self.context_compressor` / `self.tools` / `self._memory_manager` / `self._session_db` 속성
- [x] `engine/NOTICE.md` 갱신 (5 Vendor copy + 1 Port + 1 어댑터)
- [x] `tests/unit/test_compression.py` — 13개 단위 테스트 (lazy, idempotent, model metadata, token estimate, surface)
- [x] 전체 32/32 단위 테스트 green @ 7.3s
- [x] smoke test 5s, HTTP 200, REPORT.md 정상

**Drop 결정 (Phase 2 이상으로 미룸)**:
- `trajectory_compressor.py` 1,467라인 (batch learning CLI, fire/rich 의존)
- auxiliary_client 의 5개 다중 provider 어댑터 (OpenAI/Codex/Copilot/Nous/Async 시리즈)
- model_metadata 의 9단계 fallback chain (cache → live probe → models.dev → ...)

## 단위 6 — memory manager Vendor copy ✅ 완료 (2026-05-13)

**실측 결과**: memory_provider.py 218라인 (의존 0), memory_manager.py 475라인 (의존 2개: memory_provider + tools.registry.tool_error). 둘 다 Vendor copy 가능.

차용 결과:

- [x] `engine/learning/memory_provider.py` — Vendor copy (218라인, 0-line modification)
- [x] `engine/learning/memory_manager.py` — Vendor copy (475라인, import 2줄만 engine.* 로 변경)
- [x] `engine/tools/registry.py` — Vendor copy (`tool_error` + `tool_result` 선택 발췌, 단위 8 의 자리잡기)
- [x] AIAgent 확장: `_attach_memory_manager(mgr)` + `_memory_prefetch_safe(query)` + `_compress_context` 의 `on_pre_compress` hook (None 가드)
- [x] `tests/unit/test_memory.py` — 9개 단위 테스트
- [x] **invariant 검증**: 메모리 없어도 (`_memory_manager = None`), 빈 manager 도, 예외 던지는 provider 도 모두 *에러 없이* `""` 반환. 단위 테스트 6개로 보장.
- [x] 전체 41/41 단위 테스트 green @ 10s
- [x] smoke test (단위 6 변경 후 회귀 검증)

**Drop 결정**: 외부 provider (Honcho/Hindsight/Mem0 등) 의 *구현 파일* 은 Phase 2/3 시점에 *선택적* 으로. Phase 1 시 에이전트 시나리오는 *built-in provider* 만으로 충분 (단위 7 의 skill_utils 가 SOUL.md/USER.md 와 합쳐지면).

**남은 단위 7/4 의존성**: 단위 4 (prompt builder) 의 `build_context_files_prompt` 가 *memory_manager.build_system_prompt()* 를 호출. 단위 4 시점에 자동 wire.

## 단위 7 — skill utils Vendor copy ✅ 완료 (2026-05-13)

**실측**: skill_utils.py (399라인), skill_preprocessing.py (105라인) 는 **단위 2 시점에 이미 Vendor copy** 됨. 단위 7 의 *진짜* 추가 작업은 `skill_commands.py` (421라인) + `display_hermes_home()` 보강.

차용 결과:

- [x] `engine/skills/utils.py` ← 단위 2 에서 이미 (424라인)
- [x] `engine/skills/preprocessing.py` ← 단위 2 에서 이미 (120라인)
- [x] `engine/skills/commands.py` — Vendor copy (421라인, import 2줄만 engine.* 로 변경)
- [x] `engine/storage/agent_home.py` 에 `display_hermes_home()` 추가
- [x] AIAgent 에 `valid_tool_names: set` 속성 (단위 4 prompt builder 가 의지)
- [x] `_attach_memory_manager` 가 provider tool 이름을 `valid_tool_names` 에 자동 합침
- [x] `tests/unit/test_skills_wiring.py` — 10개 단위 테스트 (display_hermes_home 2개 + 모듈 import 3개 + valid_tool_names 4개 + disabled 1개)
- [x] 전체 51/51 단위 테스트 green @ 12s
- [x] smoke test 회귀 검증

**보류**: skill 디렉터리 watch / hot reload — Phase 2 또는 단위 10 (API 서버) 단계.

## 단위 8 — Tool 시스템: skill_manage + 경량 file ops ✅ 완료 (2026-05-13)

**범위 조정 (옵션 A, 사용자 결정 2026-05-13)**: 시 에이전트 시나리오 (Phase 1 (B)) 의 핵심은 *skill 자동 생성/수정/삭제*. terminal_tool (2041라인) 은 Drop — 시 에이전트는 대화 중심이라 셸 명령 미사용. file_tools/file_operations (2600라인) 도 경량 Port 로 read/write/list 3개만.

차용 결과:

- [x] `engine/skills/manager.py` — Vendor copy of `tools/skill_manager_tool.py` (788라인, 7 import 변경: 4 top-level + 3 lazy)
- [x] `engine/tools/path_security.py` — Vendor copy (32라인, 0-line modification)
- [x] `engine/tools/file_ops.py` — Independently authored (read_file/write_file/list_files + write 화이트리스트). Hermes file_tools 2600라인 대신 ~200라인
- [x] `engine/skills/_cfg_stub.py` — Phase 1 stub for `hermes_cli.config.cfg_get`
- [x] `engine/storage/atomic.py` 에 `is_truthy_value` 추가
- [x] `engine/tools/registry.py` 에 `_ToolRegistry` stub 추가 (vendored `registry.register(...)` 호환)
- [x] `engine/tools/skill_view.py` 에 `build_skill_view_tool()` factory 추가
- [x] `engine/skills/__init__.py` 에 `build_default_skill_tools()` 추가 — skill_view + skill_manage 묶음
- [x] AIAgent 에 `register_default_tools(include_file_ops=True)` helper — Phase 1 default 5-tool catalogue (skill_view, skill_manage, read_file, write_file, list_files). Idempotent.
- [x] **보안**: write 는 agent home 안으로만 (path_security.validate_within_dir), `..` traversal 거절. 단위 테스트 2개로 보장.
- [x] `tests/unit/test_tools_unit8.py` — 9개 단위 테스트
- [x] 전체 73/73 단위 테스트 green @ 19.7s
- [x] smoke test 회귀 검증

**Drop 결정 (Phase 2 이상으로 미룸)**:
- `tools/terminal_tool.py` 2041라인 — 셸 명령 실행 (Phase 1 시 에이전트 미사용)
- `tools/file_tools.py` + `file_operations.py` 의 fuzzy match patch, snapshot, image preview, Office parsing 등 모든 고급 기능
- `tools/skills_tool.py` 1301라인 (`skills_list` / `skills_describe` etc.) — `skill_view` 로 대체
- `tools/checkpoint_manager.py`, `tools/process_registry.py`, `tools/tirith_security.py` 등 보안/안전망 — Phase 3

## 단위 9 — session search (FTS5) Vendor copy ✅ 완료 (2026-05-13)

**범위 결정 (옵션 A 사용자 결정 2026-05-13)**: Hermes 의 hermes_state.py (2689라인) + session_search_tool.py (543라인) 적극 차용. **멀티테넌트 격리 = per-user agent_home** (UBION_AGENT_HOME). 코드는 1인 가정 유지, Phase 3 컨테이너화로 자연 분리.

차용 결과:

- [x] `engine/storage/session_db.py` — Vendor copy of `hermes_state.py` (2689라인, import 2줄만 engine.* 로 변경). FTS5 + CJK trigram + WAL fallback + 마이그레이션 v1~v11 모두 포함
- [x] `engine/tools/session_search.py` — Vendor copy of `session_search_tool.py` (543라인, import 6줄 변경: 2 top-level + 4 lazy)
- [x] `engine/llm/aux_client.py` 확장 — `async_call_llm` (asyncio.to_thread wrapper), `_run_async` (sync→async bridge), `extract_content_or_reasoning` (think block stripping)
- [x] AIAgent.`_ensure_session_db()` lazy + `register_default_tools(include_session_search=True)` 기본 활성
- [x] `engine/tools/__init__.py` 에 `build_session_search_tool()` factory
- [x] `tests/unit/test_session_db.py` — 9개 단위 테스트 (lazy/idempotent, 격리, FTS5 sanitise, end-to-end roundtrip)
- [x] 전체 82/82 단위 테스트 green @ 22.2s
- [x] smoke test 회귀 검증

**격리 결정 기록**: PROJECT_SPEC §4 의 "Phase 1 = 로컬 1인" 범위 유지. 멀티테넌트는 Phase 3 인프라 의제 (memory:project_tenancy_strategy.md). 코드 변경 0.

### Workspace 개념 추가 (2026-05-13, 단위 9 후속)

사용자 요구: "자기가 원하는 파일을 토대로 대화 가능". UBION_AGENT_HOME (영속 상태) + 별도 UBION_WORKSPACE (작업 대상 폴더) 분리:

- [x] `engine/storage/agent_home.py` 에 `get_workspace()` 추가 — UBION_WORKSPACE env → Path, fallback cwd
- [x] AIAgent._build_system_prompt() 가 workspace 를 `build_context_files_prompt(cwd=workspace)` 로 전달
- [x] `tests/unit/test_workspace.py` 7개 단위 테스트 — workspace 전환 시 AGENTS.md 가 system prompt 에 자동 합쳐짐 직접 검증
- [x] 메모리: project_workspace_concept.md

**의미**: SOUL.md (에이전트 정체성) 은 agent_home 안. HERMES.md/AGENTS.md/CLAUDE.md/.cursorrules (프로젝트 정체성) 은 workspace 안. 같은 시 에이전트 인격으로 다른 폴더 작업 가능. 환경변수만 바꿔서 유연 전환.

## 단위 10 — OpenAI 호환 API 서버 ✅ 완료 (2026-05-13)

**프레임워크 결정 (사용자 2026-05-13)**: aiohttp 분할계획 → **FastAPI + uvicorn** 으로 변경. 사유: OpenAPI 자동, pydantic 검증, TestClient 내장, Phase 2/3 확장 용이.

차용 강도: Reference (자체 작성, Hermes 코드 보지 않음).

- [x] `engine/server/api.py` 자체 작성 (FastAPI app + ChatCompletion/Models/Health endpoints)
- [x] `/v1/chat/completions` — non-stream + stream(SSE) 양쪽 지원
- [x] `/v1/models` — claude-opus-4-7 / sonnet-4-6 / haiku-4-5 노출
- [x] `/health` — auth 없이도 접근 (uptime probe 용)
- [x] Bearer token auth — `UBION_API_TOKEN` env. 비어있으면 auth 비활성 (로컬 기본)
- [x] streaming SSE — `data: {chunk}\n\n` + `data: [DONE]\n\n`
- [x] `engine/server/__main__.py` — `python -m engine.server` 실행 진입점
- [x] OpenAI message → AIAgent 변환 (마지막 user 가 user_message, 그 앞은 conversation_history, system 은 drop)
- [x] AIAgent 가 sync 라 `asyncio.to_thread` 로 워커 스레드 위임 → FastAPI 이벤트 루프 응답성 유지
- [x] `tests/unit/test_api_server.py` — 11개 단위 테스트 (TestClient + FakeAgent factory patch)
- [x] 전체 100/100 단위 테스트 green @ 24s
- [x] curl/HTTP client 로 end-to-end 검증

**보류 (Phase 2/3)**:
- 진짜 token-by-token streaming (현재는 응답 받아서 chunk 분할; AnthropicClient 의 native streaming 연동 필요)
- Gateway 세션 캐시 (LRU + TTL) — Phase 2 multi-session 시
- CORS, rate limit, audit log — Phase 3 운영
- WebSocket / gRPC 인터페이스 — 필요시 추후

## 단위 13 — 다중 provider 지원 (DeepSeek 추가) ✅ 완료 (2026-05-13)

**사유**: Phase 1 (B) 시 에이전트 1주 시나리오에서 DeepSeek API 도 사용하고 싶다는 사용자 요구. 단위 2 "Anthropic 단일 정책" 폐기. DeepSeek 는 OpenAI 호환 API 라 `openai` SDK 의 base_url 만 바꿔 통합.

차용 결과:

- [x] `engine/llm/deepseek.py` — OpenAI SDK wrapper, Anthropic↔OpenAI 메시지/툴 양방향 변환 (236라인)
- [x] `engine/llm/router.py` — provider router (model name prefix 기반, explicit override 허용)
- [x] AIAgent.__init__ 가 router 통해 자동 provider 인식 + client 인스턴스화 (한 줄 변경)
- [x] `engine/server/api.py` 의 `/v1/models` 에 `deepseek-v4-flash`, `deepseek-v4-pro` 추가
- [x] `/v1/chat/completions` 가 request.model 기반 routing (AIAgent 가 자동 처리)
- [x] `DEEPSEEK_API_KEY` env 처리 (DeepSeekClient 가 검증)
- [x] `engine/learning/model_metadata.py` 에 `_DEEPSEEK_CONTEXT_LENGTHS` catalog (128K 통일)
- [x] `tests/unit/test_multi_provider.py` — 19개 단위 테스트
- [x] 전체 119/119 단위 테스트 green @ 26s
- [x] curator smoke test 회귀 검증

**핵심 설계**:
- 양 provider 의 client 가 같은 `chat(messages, system, tools, max_tokens) -> ChatResponse` surface 보유 → agent 루프는 provider 무지각
- DeepSeek 응답을 Anthropic 형태 `ChatResponse` 로 정규화 → tool dispatch 코드 동일하게 작동
- Anthropic native `tool_use`/`tool_result` 블록 ↔ OpenAI `tool_calls`/`role: tool` 양방향 변환

**보류 (Phase 2 이상)**:
- aux_client (context compressor 용) 는 여전히 Anthropic-only — 다중 provider 필요해질 때 확장
- model_metadata 의 9단계 fallback chain 은 단순화 유지 (Anthropic + DeepSeek 두 catalog 만)
- provider fallback chain (DeepSeek 죽으면 Anthropic 으로 자동) — 분할 계획 C29 와 일관, Phase 2

## 단위 12 — 자체 웹앱 UI (Open WebUI 참고) — 사용자 결정 2026-05-13

**범위 (B)**: chat 핵심 + skill 보기/편집 + memory 관리 + 설정 패널.

**프레임워크**: React + TypeScript + Vite + Tailwind (Open WebUI 와 유사 스택). pnpm/npm 중 결정.

**디렉토리**: 본 트리 루트의 `web/` 또는 별도 디렉토리. Phase 3 에서 컨테이너화 시 위치 결정.

**기능 명세** (1차):

- [ ] 채팅 화면
  - [ ] 세션 목록 사이드바
  - [ ] 메시지 버블 (user / assistant / system / tool_use / tool_result)
  - [ ] streaming SSE 렌더 (단위 10 의 `/v1/chat/completions`)
  - [ ] 모델 선택 dropdown (claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5, deepseek-chat, deepseek-reasoner — 단위 13 후)
  - [ ] Workspace 표시 + 변경 UI
- [ ] Skill 패널
  - [ ] 등록된 skill 리스트 (skill_view 기반)
  - [ ] skill 클릭 시 SKILL.md 본문 보기
  - [ ] skill 수동 편집 / 새로 추가 / 삭제 (skill_manage tool)
  - [ ] 자동 생성된 skill 표시
- [ ] Memory 패널
  - [ ] memory 항목 리스트 (memory_manager.build_system_prompt 기반)
  - [ ] 항목 보기 / 수정 / 삭제
- [ ] 설정 패널
  - [ ] API 키 입력 (Anthropic, DeepSeek)
  - [ ] UBION_AGENT_HOME 표시
  - [ ] UBION_WORKSPACE 폴더 선택 (file picker)
  - [ ] Bearer token 설정
- [ ] Session search 패널 (선택적) — 단위 9 활용
- [ ] 단위 테스트 (Playwright 또는 Vitest)
- [ ] `python -m engine.server` 와 함께 실행하는 통합 스크립트

**보류 (Phase 2 이상)**:
- 다중 사용자 / 권한 / OAuth
- audit log 패널
- 운영 dashboard
- 모바일 반응형

## 단위 11 — 자동 git commit + snapshot ⏸ 보류 (사용자 결정 2026-05-13)

**사유**: 1) Phase 1 (B) 시 에이전트 1주 시나리오에서 *어떤 트리거 정책이 실제로 유용한지* 모름. 1주 사용 결과를 보고 정하는 게 정합. 2) 멀티유저/Phase 3 의 git 정책과 충돌 가능. 3) 보류 동안 사고 시 *수동 rollback* 으로 충분.

### Phase 1 (B) 진행 동안의 수동 rollback 절차

1. 시나리오 시작 *직전* 에 사용자가 `~/.ubion-agent/` (또는 `UBION_AGENT_HOME` 가 가리키는 경로) 에서 `git init` + `git add . && git commit -m "scenario-start"`
2. 부적절한 skill 자동 생성 / 메모리 손상 발견 시 `git checkout .` 또는 `git reset --hard scenario-start`
3. 매일 끝 (시나리오 측정 항목 기록 후) 에 `git add . && git commit -m "day-N"` 로 수동 스냅샷
4. 1주 후 회고 시 `git log` 로 *언제 어떤 skill/memory 가 생겼는지* 추적 가능

→ 자동화는 단위 11 의 *진짜 의미가 입증된 뒤* (Phase 1 (B) 회고 시점) 진행.

차용 대상 (보류 중 보존): `agent/curator_backup.py` (snapshot) + Hermes 자동 commit 로직

- [ ] git auto-commit 트리거 정책 결정 (Phase 1 (B) 회고 후)
- [ ] snapshot 디렉터리 구조
- [ ] rollback 명령

## Phase 1 종료 검증

- [ ] 자체 엔진 단독 실행 가능 (`python -m engine.server.api`)
- [ ] curl/HTTP client로 메시지 송수신 동작
- [ ] tool 호출 (terminal, file) 실행 성공
- [ ] skill 자동 생성/큐레이션 루프 동작 (sandbox 시범과 동등하거나 우월)
- [ ] memory 큐레이션 루프 동작
- [ ] `~/.ubion-agent/` 디렉터리에 영속 상태 보존
- [ ] git auto-commit 동작
- [ ] 1주 사용 후 누적 비용 측정

## Phase 1 Gate

- 🟢 GREEN — 자체 엔진이 ax 센터 1인 로컬 환경에서 안정 동작 + 자기진화 루프 검증 → Phase 2 진입 (운영 정책 문서화 + Phase 3 인프라 설계)
- 🟡 YELLOW — 핵심 동작은 되지만 비용/안정성/UX 중 한 축이 불안정 → 보완
- 🔴 RED — 자체 엔진 구현이 비현실적으로 큼 → 옵션 A로 후퇴 재검토

## 산출물

- [ ] `engine/` 자체 엔진 코드베이스
- [ ] `engine/NOTICE.md` 차용 출처 일괄 정리
- [ ] `research/run-agent-split-plan.md`
- [ ] `research/phase-1-retrospective.md`
- [ ] `research/phase-2-todo.md` 옵션 C 반영 갱신

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-13 | v0.1 초안 (옵션 A 기준 2인 PoC) |
| 2026-05-13 | **전면 재작성** — v0.2 옵션 C 반영, 로컬 개발 범위, 11단계 차용 작업 분해 |
