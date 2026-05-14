# Phase 0 TODO — 차용 가능성 검증

## 목적

Hermes의 핵심 모듈을 우리 코드베이스로 떼어내어 흡수할 수 있는지를 **실제 시범 포팅**으로 검증한다. 첫 시범 대상은 **skill 자동 생성 루프**.

Phase 0의 의제가 v0.1에서 변경되었다 (PROJECT_SPEC v0.2):
- ~~기존: Hermes를 직접 써보고 자기진화의 업무 가치 검증~~
- **신규: Hermes 코드를 우리가 떼어낼 수 있는지, 우리 코드베이스로 흡수할 수 있는지 검증**

## 전제

- 엔진 전략: 옵션 C (자체 구현 + Hermes 사상/코드 차용). PROJECT_SPEC §2.2 참조.
- 일정 제약: 없음. 프로토타입 우선.
- 언어: Python.
- 업스트림 추적: 안 함.

## 메타

- 담당자: ax 센터
- 시작일: 2026-05-13
- 종료일: 미정 (차용 시범 완료 시점)
- Hermes 차용 기준 커밋: `.hermes-clone/` shallow clone HEAD (2026-05-13)
- 모델 제공자: 미정
- 시범 포팅 LLM 호출 예산 상한: 기입 필요

## 0. 시작 조건

- [x] `.phase` 파일 = `0`
- [x] PROJECT_SPEC v0.2 갱신 완료
- [x] AGENT.md 차용 정책 갱신 완료
- [x] `research/hermes-message-interface.md` 완료 — 외부 메시지 인터페이스 = OpenAI 호환 API server (차용 대상)
- [ ] sandbox 작업 위치 `sandbox/skill-loop-port/` 확정
- [ ] Hermes shallow clone 커밋 SHA 기록
- [ ] 시범 포팅용 LLM API key + 비용 상한 기입

## 1. 사전 조사 — 차용 정책 수립

### 1.1 모듈 지도 + 차용 강도 매트릭스

- [x] `research/hermes-code-walkthrough.md` 작성
  - Hermes 디렉터리/모듈 전수 정리
  - 모듈별 차용 강도: Vendor copy / Port / Reference / Drop
  - 모듈 간 의존성 그래프 (적어도 1차 의존)
  - "본 프로젝트가 안 가져오는 것" 명시 리스트

### 1.2 라이선스 정책

- [x] `research/hermes-license-policy.md` 작성
  - MIT 라이선스 헤더 템플릿 (Python 파일용)
  - 출처 표기 규칙: `Adapted from NousResearch/hermes-agent (MIT) — original: <path>@<commit>`
  - 수정 내역 기록 방식
  - Phase 1 CI에서 헤더 누락 체크 방안 (초안)

### 1.3 사내 보안 정책 1차 질의 (병행)

- [ ] 사내 보안팀 접촉 시작
  - 자율 bash 실행 권한
  - 외부 LLM API 호출
  - 사용자별 격리 수준
- [ ] `research/security-policy-check.md` 1차 답변 채우기

## 2. 첫 차용 시범 — skill 자동 생성 루프

### 2.1 시범 계획 작성

- [x] `research/skill-loop-port-feasibility.md` 작성

### 2.2 sandbox 시드

- [x] `sandbox/skill-loop-port/` 디렉터리 생성
- [x] `sandbox/skill-loop-port/README.md`
- [x] `sandbox/skill-loop-port/NOTICE.md`
- [x] `sandbox/skill-loop-port/.gitignore`

### 2.3 코드 차용 실행

- [x] **Vendor copy**: `curator.py`, `skill_usage.py` — Hermes 원본 0줄 수정, MIT 헤더 prepend만
- [x] **Port**: `agent_home.py` — `get_hermes_home` Port, `UBION_AGENT_HOME` env로 재명명
- [x] **Shim** (자체): `hermes_constants.py`, `tools/__init__.py`, `run_agent.py` — 3개 shim으로 vendored import 경로 그대로 유지
- [x] `requirements.txt` — anthropic, python-dotenv

### 2.4 End-to-end 실행 1회 성공

- [x] `run_demo.py` 작성
- [x] LLM API 실제 호출 발생: Opus 4.7, 21.16초, 약 $0.40
- [x] curator review 정상 완료: 5 skills → 2 클러스터 식별, REPORT.md + run.json 생성
- [x] LLM 출력 정성 평가: 9/10 (umbrella 통합 전략 정확)
- [x] `output/run-20260513T042835Z.log`에 보관

### 2.5 변형 실험

- [x] 빈 fixtures → `skipped (no candidates)` 종료, LLM 호출 0
- [x] `set_paused(True)` → `should_run_now=False`, `maybe_run_curator=None`

### 2.6 시범 회고

- [x] `research/skill-loop-port-feasibility.md §5` 채움
  - 차용된 코드 줄 수 / Hermes 원본 줄 수 비율
  - 포팅 작업 시간 (인시)
  - LLM 비용 (시범 1회 + 누적)
  - 의존성 절단 작업 난이도 (정성)
  - 무엇이 쉬웠고 무엇이 어려웠는지
  - 다른 모듈에도 같은 패턴이 통할지 예측

## 3. Phase Gate 판정

- [x] **🟢 GREEN — 차용 시범 성공** (2026-05-13)
  - skill 자동 생성 루프 단독 실행 가능 ✅
  - end-to-end 1회 통과 (LLM 21초, REPORT.md 생성) ✅
  - 코드 이해도 충분 — vendor copy + shim 패턴이 일반화 가능 ✅
  - 차용 비율 85%, vendored 파일 0줄 수정, 미해결 의존성 0개 ✅
  - → 나머지 모듈 차용 + Phase 1 진행
- [ ] 🟡 YELLOW — 해당 없음
- [ ] 🔴 RED — 해당 없음

세부 판정 근거: [`phase-0-retrospective.md`](phase-0-retrospective.md), [`skill-loop-port-feasibility.md §5`](skill-loop-port-feasibility.md)

## 4. 종료 산출물 체크

- [x] `research/hermes-code-walkthrough.md`
- [x] `research/hermes-license-policy.md`
- [x] `research/skill-loop-port-feasibility.md` (회고 §5 포함)
- [x] `sandbox/skill-loop-port/` — 동작하는 차용 코드 + 출력 샘플
- [x] `research/phase-0-retrospective.md` GREEN 판정 기록
- [ ] `research/phase-1-todo.md` 옵션 C 반영 — **Phase 1 진입 직전 작업으로 이월**

## 완료 조건

- [x] Phase Gate 판정 선택됨: 🟢 GREEN
- [x] 판정 근거가 `phase-0-retrospective.md` + `skill-loop-port-feasibility.md §5`에 기록됨
- [x] Green → Phase 1 진입 가능 상태. 진입 시점은 사내 보안 정책 답변 + `phase-1-todo.md` 갱신 후

---

## 부록: 이전 v0.1 의제 (참고용)

v0.1에서 Phase 0의 목표는 "Hermes를 직접 써보고 자기진화의 업무 가치 검증"이었다. 이는 v0.2에서 **명시적으로 제외**된다:

- Hermes의 가치는 평판/문서/우리 사전 분석을 신뢰하고 별도 검증하지 않는다.
- 우리는 *차용 가능성*에만 집중한다.
- 만약 Phase 1 이후 실사용 가치가 의심된다면 그때 별도 검증 phase를 만든다.

이 의제 변경 합의는 2026-05-13 대화에서 이루어졌다 (PROJECT_SPEC v0.2 변경 이력 참조).
