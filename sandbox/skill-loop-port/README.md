# sandbox/skill-loop-port

> **🟢 STATUS: 승격됨 (2026-05-13)** — Phase 1 단위 1에서 본 sandbox 코드가
> `engine/` 본 트리로 옮겨졌다. 본 디렉터리는 *역사적 기록*으로 유지되며
> 더 이상 개발 대상이 아니다.
>
> - `curator.py` → `engine/learning/curator.py`
> - `skill_usage.py` → `engine/skills/usage.py`
> - `agent_home.py` → `engine/storage/agent_home.py`
> - `mock_agent.py`, `run_agent.py` shim, `tools/__init__.py` shim, `hermes_constants.py` shim → **폐기** (본 트리에서는 import 경로 직접 수정)
> - `fixtures/skills/` → `tests/fixtures/skills/`
>
> Phase 0 게이트 결과는 `research/phase-0-retrospective.md`에 보존되어 있다.

---

## 목적 (이력)

Phase 0 차용 가능성 검증의 **첫 시범 작업**이었다.

Hermes의 skill 자동 생성/큐레이션 루프(`agent/curator.py`)를 우리 코드베이스로 떼어내어 단독 실행 가능하게 만든다. 성공하면 옵션 C (자체 구현 + Hermes 사상/코드 차용) 전략이 검증된 것이다.

## 상위 컨텍스트

- **프로젝트 전체 명세**: [`../../PROJECT_SPEC.md`](../../PROJECT_SPEC.md)
- **시범 포팅 계획서**: [`../../research/skill-loop-port-feasibility.md`](../../research/skill-loop-port-feasibility.md) ← 작업 순서는 이 문서를 따른다
- **모듈별 차용 강도 매트릭스**: [`../../research/hermes-code-walkthrough.md`](../../research/hermes-code-walkthrough.md)
- **라이선스 정책**: [`../../research/hermes-license-policy.md`](../../research/hermes-license-policy.md)

## 작업 위치 의미 (sandbox라는 것)

이 디렉터리는 **격리된 시범 작업 공간**이다. Phase 0 게이트 결과에 따라:

- 🟢 GREEN — `engine/learning/` 등으로 *승격*. sandbox 코드는 그대로 옮기거나 정제.
- 🟡 YELLOW — 보완 작업 진행. sandbox 위치 유지.
- 🔴 RED — 폐기. 옵션 A로 후퇴.

본 트리(`engine/`, `dispatcher/` 등)를 시범 코드로 오염시키지 않는 게 sandbox의 존재 이유다.

## 차용 원본

- 저장소: https://github.com/NousResearch/hermes-agent
- 라이선스: MIT (Copyright 2025 Nous Research)
- 기준 커밋: `b06e9993021a8eebd891fc60d52372446315b2f0` (2026-05-12)
- 차용 대상: `agent/curator.py` (1,781 라인) + 의존성

전체 라이선스 텍스트와 파일별 출처는 [`NOTICE.md`](NOTICE.md) 참조.

## 디렉터리 구조 (계획)

```
skill-loop-port/
├── README.md          ← 이 파일
├── NOTICE.md          ← Hermes MIT 라이선스 + 파일별 출처
├── .gitignore         ← venv, __pycache__, output/
├── requirements.txt   ← anthropic, python-frontmatter, pytest
├── agent_home.py      ← Ported from hermes_constants.py
├── skill_usage.py     ← Adapted from tools/skill_usage.py
├── curator.py         ← Adapted from agent/curator.py (★ 핵심)
├── mock_agent.py      ← 자체 작성 — 최소 AIAgent mock
├── run_demo.py        ← 자체 작성 — end-to-end 실행 스크립트
├── fixtures/
│   └── skills/        ← 시범용 가짜 agent-created skill 3~5개
└── output/            ← 실행 로그, 생성된 skill 샘플 (git ignored)
```

## 실행 방법 (작업 완료 시점에 갱신)

```bash
# 작업 진행 전이라 아직 동작하지 않음. 시범 포팅 §3.6 단계에서 채움.
python -m venv .venv
source .venv/Scripts/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python run_demo.py
```

## 현재 상태

- [x] 디렉터리 시드 완료 (README, NOTICE, .gitignore)
- [ ] 의존성 측정 — [skill-loop-port-feasibility.md §3.2](../../research/skill-loop-port-feasibility.md)
- [ ] 코어 차용 시작 — §3.3
- [ ] Mock AIAgent — §3.4
- [ ] Fixtures — §3.5
- [ ] End-to-end 실행 — §3.6
- [ ] 회고 작성 — §5

진행 상황은 [`../../research/skill-loop-port-feasibility.md`](../../research/skill-loop-port-feasibility.md)에서 추적한다.
