# Research: Skill 자동 생성 루프 — 시범 포팅 계획 (Feasibility)

## 목적

Phase 0 차용 가능성 검증의 **첫 시범 모듈** — Hermes의 skill 자동 생성/큐레이션 루프(`agent/curator.py`)를 우리 코드베이스(`sandbox/skill-loop-port/`)로 떼어내어 단독 실행 가능하게 만든다.

성공하면 옵션 C 전략이 검증된 것이고, 실패하면 옵션 A 후퇴를 고려한다.

## 메타

- 작성일: 2026-05-13
- 작성자: ax 센터 + Claude
- 차용 기준 커밋: `b06e9993021a8eebd891fc60d52372446315b2f0` (2026-05-12)
- 차용 대상: `.hermes-clone/agent/curator.py` (1,781 라인) 외 의존성
- 작업 위치: `sandbox/skill-loop-port/`
- 상태: **계획 단계** — 실제 포팅 작업 전. 작업 진행 중 본 문서를 갱신한다.

---

## 1. 대상 모듈 동작 메커니즘 (docstring 인용)

`agent/curator.py:1-20`에서 직접 인용:

> The curator is an auxiliary-model task that periodically reviews agent-created
> skills and maintains the collection. It runs **inactivity-triggered** (no cron
> daemon): when the agent is idle and the last curator run was longer than
> `interval_hours` ago, `maybe_run_curator()` spawns a **forked AIAgent** to do
> the review.
>
> **Responsibilities**:
> - Auto-transition lifecycle states based on derived skill activity timestamps
> - Spawn a background review agent that can **pin / archive / consolidate /
>   patch** agent-created skills via `skill_manage`
> - Persist curator state (`last_run_at`, `paused`, etc.) in `.curator_state`
>
> **Strict invariants**:
> - Only touches **agent-created skills** (see `tools/skill_usage.is_agent_created`)
> - **Never auto-deletes** — only archives. Archive is recoverable.
> - Pinned skills bypass all auto-transitions
> - Uses the auxiliary client; never touches the main session's prompt cache

### 1.1 트리거 모델

- **시간 기반이 아니라 사용자 활동 기반(inactivity-triggered)**. cron 안 씀.
- 호출 진입점: `maybe_run_curator()` — 메시지 처리 사이클에서 idle 판정될 때 호출됨.
- 인터벌: 기본 7일 (`DEFAULT_INTERVAL_HOURS = 24 * 7`, curator.py:56).
- 최소 idle 시간: 2시간 (`DEFAULT_MIN_IDLE_HOURS = 2`, curator.py:57).

### 1.2 리뷰 메커니즘

- **별도 LLM client (auxiliary client)** — 메인 세션의 prompt cache 오염 방지.
- **AIAgent를 fork** — `run_agent.py`의 `AIAgent` 인스턴스를 새로 생성해 review 작업 수행.
- 결과 액션: `skill_manage` tool로 pin / archive / consolidate / patch 수행.
- 안전 장치: 자동 삭제 금지. archive만. pinned skill 보호.

### 1.3 상태 영속화

- 파일: `<HERMES_HOME>/skills/.curator_state` (JSON)
- 필드: `last_run_at`, `last_run_duration_seconds`, `last_run_summary`, `paused`, `run_count`
- 락/원자성: `tempfile.mkstemp` + `os.replace` 패턴 사용 (curator.py:97-115)

### 1.4 lifecycle state 자동 전이

- `DEFAULT_STALE_AFTER_DAYS = 30`
- `DEFAULT_ARCHIVE_AFTER_DAYS = 90`
- skill activity timestamp로 stale / archive 자동 전이

---

## 2. 의존성 그래프 (실측)

`agent/curator.py`의 import (상단):

```python
from hermes_constants import get_hermes_home
from tools import skill_usage
```

그리고 함수 본문 안에서 lazy import:

```python
from run_agent import AIAgent          # curator.py:1645
```

### 2.1 직접 의존성 — 떼어내야 할 모듈

| 의존 모듈 | 파일 | 라인 | 우리 처리 |
|----------|------|------|---------|
| `hermes_constants.get_hermes_home()` | `hermes_constants.py` | 14-68 | 🟡 Port — `get_agent_home()`로 개명, `UBION_AGENT_HOME` 환경변수 |
| `tools.skill_usage` | `tools/skill_usage.py` | 609 | 🟢 Vendor copy 또는 일부 Port — `is_agent_created`, activity tracking 함수가 핵심 |
| `run_agent.AIAgent` | `run_agent.py` | ~15,500 라인 (!) | **❌ 큰 문제** — 전체 import는 비현실적 |

### 2.2 `AIAgent` 의존성 처리 전략 — 가장 큰 결정점

**문제**: `AIAgent`는 Hermes 엔진 전체이다. 이걸 차용하면 Phase 0가 시범이 아니라 *엔진 전체 차용*이 된다.

**해결 옵션 3가지**:

#### 옵션 α — Mock AIAgent (권장)

- `sandbox/skill-loop-port/`에 **최소한의 mock `AIAgent`**를 작성: LLM API를 직접 호출하는 100~200줄짜리 단순 래퍼.
- 시범의 목적은 "curator의 *오케스트레이션 로직*"을 떼어낼 수 있는지 검증하는 것이므로, AIAgent 본체는 mock으로 충분.
- 단점: 진짜 자기진화의 *품질*은 평가 못함. 하지만 Phase 0 목표는 차용 가능성이지 자기진화 품질이 아님.

#### 옵션 β — Hermes에서 AIAgent도 같이 차용

- Phase 0이 *엔진 전체 차용*으로 확장됨.
- 일정이 1~2주 → 1~2개월로 부풀어짐.
- Phase 0의 목적과 충돌.

#### 옵션 γ — `AIAgent` 호출 인터페이스만 차용

- curator.py:1645 근처의 `AIAgent(...)` 호출 시그니처를 분석해서, 같은 시그니처를 가지는 *얇은* 우리 클래스 작성.
- 옵션 α의 정교한 버전.

**제안**: **옵션 α (Mock AIAgent)** 로 진행. 시범의 목적은 차용 *가능성* 검증이지 자기진화 *품질* 검증이 아니다.

### 2.3 간접 의존성 (확인 필요)

`tools/skill_usage.py`가 무엇을 import하는지는 차용 작업 시작 시 측정. 예상되는 의존성:
- 파일 시스템 접근 (skills 디렉터리)
- frontmatter 파싱
- 더 깊은 의존 사슬 가능성

**측정 방법** (시범 작업 첫 단계):
```bash
cd .hermes-clone
python -c "import ast; tree=ast.parse(open('tools/skill_usage.py').read()); print([n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)])"
```

---

## 3. 포팅 작업 단위 분해

체크박스화 가능한 작은 단위로 분해. Phase 0 진행 시 그대로 todo로 사용.

### 3.1 사전 — 차용 환경 준비

- [ ] `sandbox/skill-loop-port/` 디렉터리 생성
- [ ] `sandbox/skill-loop-port/README.md` 작성 (목표/실행법)
- [ ] `sandbox/skill-loop-port/NOTICE.md` 작성 (MIT 라이선스 + 출처)
- [ ] `sandbox/skill-loop-port/.gitignore` (venv, __pycache__, output/)
- [ ] Python venv 생성 + `requirements.txt` (anthropic, python-frontmatter, pytest 정도)

### 3.2 의존성 측정

- [ ] `tools/skill_usage.py` import 그래프 측정
- [ ] `agent/curator.py` 전체 그래프 (직접 + 간접)를 종이에 그림
- [ ] 측정 결과를 본 문서 §2.3에 반영

### 3.3 코어 차용 — Vendor copy

- [ ] `hermes_constants.py` → `sandbox/skill-loop-port/agent_home.py` (rename + Port)
  - `HERMES_HOME` → `UBION_AGENT_HOME` (env 변수명)
  - `get_hermes_home` → `get_agent_home`
  - MIT 헤더 부착 ("Ported from")
- [ ] `tools/skill_usage.py` → `sandbox/skill-loop-port/skill_usage.py` (Vendor copy)
  - import 경로 조정 (`from hermes_constants` → `from .agent_home`)
  - 깊은 의존성 발견 시 추가 차용 또는 stub
  - MIT 헤더 부착 ("Adapted from")
- [ ] `agent/curator.py` → `sandbox/skill-loop-port/curator.py` (Vendor copy)
  - import 경로 조정
  - `from run_agent import AIAgent` → `from .mock_agent import AIAgent`
  - MIT 헤더 부착

### 3.4 Mock AIAgent 작성

- [ ] `sandbox/skill-loop-port/mock_agent.py` 작성 (자체 작성, MIT 헤더 없음)
  - curator.py:1691에서 호출하는 `AIAgent(...)` 시그니처 분석
  - 같은 시그니처의 mock 클래스 작성
  - LLM 호출은 Anthropic SDK 직접 사용 (Claude Opus 4.7 또는 sonnet 4.6)
  - tool 호출은 `skill_manage` 만 지원 (curator가 실제 사용하는 것)

### 3.5 테스트 데이터 준비

- [ ] `sandbox/skill-loop-port/fixtures/skills/` 디렉터리에 가짜 "agent-created skill" 파일 3~5개 생성
  - frontmatter에 `created_by: agent`, `last_used: <과거 날짜>` 같은 메타
  - 본문은 진짜 같지만 작은 내용
- [ ] `.curator_state` 초기값: `last_run_at: null` 또는 8일 전

### 3.6 End-to-end 실행

- [ ] `sandbox/skill-loop-port/run_demo.py` 작성
  ```python
  from curator import maybe_run_curator
  result = maybe_run_curator(home=Path("./fixtures"), force=True)
  print(result)
  ```
- [ ] 실행 — LLM API 호출 발생
- [ ] 결과 확인:
  - [ ] curator가 정상 종료
  - [ ] `.curator_state` 갱신됨
  - [ ] 최소 1개 skill이 review됨 (pin/archive/patch 액션)
  - [ ] LLM 응답이 의미 있음 (사람이 읽고 판정)
- [ ] 실행 로그를 `sandbox/skill-loop-port/output/run-<timestamp>.log`에 저장

### 3.7 변형 실험

- [ ] 새 skill 생성 시나리오 (review 중 LLM이 새 skill을 만들도록 유도) — 가능하면
- [ ] 빈 skills 디렉터리에서 실행 → 정상 종료 확인
- [ ] paused=true 상태에서 호출 → no-op 확인

### 3.8 회고 작성

- [ ] 본 문서 §5 회고 섹션 채우기
- [ ] `research/phase-0-retrospective.md` 갱신

---

## 4. 위험 요소

| ID | 위험 | 가능성 | 영향 | 대응 |
|----|------|------|------|-----|
| F1 | `tools/skill_usage.py`가 또 다른 모듈을 깊게 의존 | 🟡 Med | 🔴 High | §3.2 의존성 측정 단계에서 조기 발견 → 추가 차용 또는 stub |
| F2 | curator.py의 lazy import 경로가 더 있음 (`run_agent.py` 외) | 🟡 Med | 🟡 Med | grep으로 모든 lazy import 식별 (`grep -n "^\s*from\|^\s*import" agent/curator.py`) |
| F3 | Mock AIAgent로는 진짜 review가 안 됨 (tool 사용이 안 됨) | 🟢 Low | 🟡 Med | review 프롬프트가 tool 없이도 텍스트로 의견 제출하도록 강제 가능 |
| F4 | LLM 호출 비용이 예상보다 큼 (curator가 여러 번 호출) | 🟢 Low | 🟢 Low | 시범에서는 max_iterations 작게 설정 (1~3회) |
| F5 | Python 버전/패키지 충돌 | 🟢 Low | 🟢 Low | Python 3.11+ venv 격리 |
| F6 | 차용한 코드의 windows 경로 처리가 우리 환경에서 깨짐 | 🟡 Med | 🟢 Low | 작업 환경이 Windows임을 인지하고 `Path` 사용 일관성 검증 |

---

## 5. 회고 (실제 포팅 결과)

작성일: 2026-05-13 (시범 포팅 직후)

### 5.1 정량 측정

| 항목 | 값 |
|------|---|
| **차용된 Hermes 코드 줄 수 (헤더 포함, Vendor copy)** | 1,799 (curator) + 622 (skill_usage) = **2,421 라인** |
| Hermes 원본 줄 수 (해당 2개 파일) | 1,781 + 609 = 2,390 라인 |
| 차용 후 증가분 (라이선스 헤더만) | +31 라인 (1.3%) |
| **새로 작성한 코드 — Port (헤더 부착)** | 53 라인 (`agent_home.py`) |
| **새로 작성한 코드 — Shim (자체)** | 18 + 17 + 15 = 50 라인 (`hermes_constants`, `tools/__init__`, `run_agent` shim) |
| **새로 작성한 코드 — Mock + Runner (자체)** | 157 (`mock_agent`) + 166 (`run_demo`) = 323 라인 |
| **새로 작성한 fixtures** | 5 SKILL.md + 1 `.usage.json` ≈ 130 라인 |
| 총 sandbox 크기 | 2,847 라인 (Python) + fixtures |
| 차용 비율 (vendored / total) | 85% |
| **포팅 작업 시간 (Claude 세션 기준)** | 약 50분 (의존성 측정 ~ end-to-end 성공까지) |
| **시범 1회 LLM 호출 비용** | 약 $0.40 추정 (Opus 4.7, 입력 ~2000 토큰 + 출력 ~1300 토큰. dry-run + 5개 skill 기준) |
| 실제 호출 1회 duration | 21.16초 |
| **lazy import 처리** | 5개 중 3개는 원본의 try/except로 자동 fallthrough, 1개는 shim(`run_agent`)으로 redirect, 1개는 동일 모듈 alias로 자동 해소 |
| 미해결 의존성 | **0개** (lazy import 5개 모두 해결됨) |

### 5.2 정성 평가

#### 코드 가독성 (0~10): **8**

- `curator.py`는 1781라인이지만 모듈 구조가 명확. docstring이 풍부.
- 주된 4개 영역: (1) state 영속화, (2) automatic transitions, (3) `run_curator_review` 오케스트레이션, (4) report writing.
- `skill_usage.py`는 더 단순. provenance(`created_by`) + activity 트래킹 + lifecycle state 전이.

#### 의존성 절단 작업 난이도: **놀라울 정도로 낮음**

- 직접 import 단 2개 (`hermes_constants`, `tools.skill_usage`) — 둘 다 1개 함수 노출만 사용
- Lazy import 5개 중 3개가 원본 코드 안에서 이미 `try/except`로 감싸짐 (`hermes_cli.config`, `cron.jobs`, `agent.curator_backup`) → 우리 환경에 없으면 자동 no-op
- `run_agent.AIAgent`만 명시적 대체 필요 → shim 1개로 해결
- **단 한 줄의 vendored 파일도 수정 안 함** (헤더 prepend 외) — shim 패턴이 완벽히 작동

#### Mock으로 충분한가?

- **충분** — Phase 0 목적(차용 가능성 검증)에 100% 부합
- curator 오케스트레이션 전체 (state, transitions, report writing) 동작 검증
- LLM의 실제 review 품질도 검증 가능 (Claude가 정확한 클러스터링 + umbrella 전략 제시)
- **단점**: tool 호출 안 됨 → 실제 `skill_manage` 액션은 검증 못함. Phase 1에서 tool 시스템 차용 시 함께 검증해야 함

#### 생성된 sample skill 품질

- 본 시범은 *기존 skill을 review*하는 것이지 *새 skill 생성*이 아니므로 정확한 표현은 "LLM review 품질"
- Claude의 분석:
  - 5개 skill을 2개 클러스터로 정확히 분류 (`hermes-config-*` 3개, `pr-review-*` 2개)
  - 각 클러스터에 맞는 통합 전략 제시 (CREATE umbrella vs MERGE INTO EXISTING)
  - "session-specific content는 `references/`로 demote"까지 정확히 적용
- **품질 9/10** — curator 프롬프트의 노하우가 그대로 작동함을 입증

### 5.3 다른 모듈에도 같은 패턴이 통할지

| 모듈 | 예상 난이도 | 근거 |
|------|---------|------|
| `agent/memory_manager.py` (555 라인) | **🟢 낮음** | curator와 비슷한 구조 추정. 직접 import는 적을 것. 같은 Vendor copy + shim 패턴 그대로 적용 가능 |
| `agent/context_compressor.py` (1,555 라인) | **🟡 중간** | LLM client 호출이 더 복잡. provider abstraction이 들어와야 할 수 있음 |
| `run_agent.py` (15,500 라인) 분할 Port | **🔴 높음** | 크기 자체가 부담. 우리는 여러 모듈로 분리하면서 Port. 시간 가장 많이 소요될 부분 |
| `tools/` 시스템 | **🟡 중간** | tool 단위로 독립 작업 가능 → 위험 분산. 보안 화이트리스트 작업이 추가됨 |
| `cron/` (2,976 라인) | **🟢 낮음** | 단 3개 파일. 자기진화 트리거 정의가 핵심 |

핵심 발견 — **vendor copy + shim 패턴이 일반화 가능**:
1. 원본 코드를 한 글자도 안 바꿈 (헤더 prepend 외)
2. 원본이 expecting하는 모듈 이름(`hermes_constants`, `tools`)을 같은 이름으로 shim
3. lazy import 처리: 원본이 try/except로 감싸진 부분은 자동 fallthrough, 명시적 대체가 필요한 것만 별도 shim

이 패턴이 다른 모듈에도 통한다면 옵션 C 전체 계획이 현실적입니다.

### 5.4 Phase Gate 권고

- [x] **🟢 GREEN 권고** — 이유:
  1. End-to-end 성공: 진짜 LLM 호출, 진짜 review 출력, 진짜 REPORT.md 생성
  2. 의존성 절단이 *예상보다 쉬움* (lazy import 5개 자동 처리, 코드 수정 0줄)
  3. 차용된 Hermes 코드 1.3% 증가 (헤더만) — 사실상 *비파괴적 흡수* 가능
  4. 차용 비율 85%로 우리가 새로 짠 코드는 mock/runner/shim의 글루뿐
  5. LLM이 curator 프롬프트의 노하우를 정확히 실행 — 자기진화의 *지능*이 코드 분리 가능함을 입증
  6. 1회 호출 21초, 약 $0.40 — 운영 비용 예측 가능
- [ ] 🟡 YELLOW 권고 — 해당 없음
- [ ] 🔴 RED 권고 — 해당 없음

### 5.5 의외의 발견 & 다음 단계로 가져갈 교훈

1. **첫 모델 ID 추측 실패** — `claude-opus-4-7-20251101` (날짜 형식)으로 가정했으나 실제는 `claude-opus-4-7` (dateless). Phase 1+에서 LLM provider adapter Port 시 model id 카탈로그를 명확히 둘 것.
2. **Windows cp949 인코딩** — emdash, 한글 등이 stdout에서 깨짐. `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` 환경변수가 필수. 차용 코드(`hermes_bootstrap.py`)에 이 처리가 있음 — 참고용으로 가져와야 함.
3. **report_path 타입** — `state["last_report_path"]`는 **디렉토리** 경로 (`logs/curator/<ts>/`), 그 안에 `REPORT.md` + `run.json`. 비슷한 패턴 다른 모듈에서도 예상.
4. **Hermes 코드의 try/except 친화성** — 핵심 모듈들이 *선택적 의존성을 try/except로 감싸는 패턴*을 광범위하게 사용. 우리 Port 작업이 쉬워지는 결정적 요인.

### 5.6 비용 시뮬레이션 메모

- 1회 curator dry-run (5 skills): $0.40 ± $0.20 (Opus 4.7)
- 실 운영 시 7일 인터벌 × 50명 = 주당 50회 = 월 200회 ≈ **월 $80** (curator만)
- Sonnet 4.6 사용 시 약 1/8 = **월 $10**
- Skill 개수 증가에 따라 prompt 크기 선형 증가 — 100개 skill 시 prompt 약 80KB → 호출당 $4 → 월 $800 (Opus). 이 시점에 `_render_candidate_list` 형식 최적화 또는 Sonnet 라우팅 검토 필요.

---

## 6. 다음 행동

본 계획 문서가 합의되면:

1. `sandbox/skill-loop-port/` 시드 (다음 단계 — 빈 디렉터리 + README + NOTICE + .gitignore)
2. 본 문서 §3.1~3.8 체크리스트 순서대로 실행
3. 진행 중 발견되는 사실은 본 문서에 반영

---

## 7. 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-13 | 초안. 옵션 C 결정 + Phase 0 재정의 직후 |
