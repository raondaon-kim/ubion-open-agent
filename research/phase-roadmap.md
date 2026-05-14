# Phase Roadmap

## 목적

실제 구현 phase는 `Phase 0`으로 유지하면서, `Phase 0~4` 전체의 계획 범위와 TODO 문서를 한곳에서 관리한다.

## 현재 상태

- 현재 구현 phase: **`1`** (2026-05-13 전환)
- 현재 작업 모드: 자체 엔진 차용 작업
- Phase 0 게이트: 🟢 GREEN (2026-05-13). `research/phase-0-retrospective.md` 참조
- 엔진 전략: **옵션 C** (자체 구현 + Hermes 사상/코드 차용) — PROJECT_SPEC v0.2 §2.2

## 문서 인덱스

- [phase-0-todo.md](phase-0-todo.md)
- [phase-1-todo.md](phase-1-todo.md)
- [phase-2-todo.md](phase-2-todo.md)
- [phase-3-todo.md](phase-3-todo.md)
- [phase-4-todo.md](phase-4-todo.md)

## Phase별 목적 요약

| Phase | 목적 | 기간 | 현재 상태 |
| --- | --- | --- | --- |
| 0 | 차용 가능성 검증 (v0.2 의제) | 단일 세션 | 🟢 GREEN (2026-05-13) |
| 1 | 자체 엔진 프로토타입 (로컬, 1인, 옵션 C) | 시간 제약 없음 | **현재 진행 중** |
| 2 | 운영 정책 정의 | Phase 1 후반 또는 병행 | 미착수 |
| 3 | 정식 멀티유저 인프라 (보안팀 게이트 활성) | 3~4주+ | 미착수 |
| 4 | 사내 정식 운영 | 지속 | 미착수 |

## 관리 원칙

- [ ] 실제 구현 phase와 계획 문서 범위를 혼동하지 않기
- [ ] Phase 이동은 gate 충족 후에만 수행
- [ ] TODO 문서는 구현 전에 먼저 정리 가능
- [ ] 각 phase TODO는 진입 조건, 작업, 검증, 산출물을 포함

## 현재 우선순위

- [x] Phase 0 차용 시범 통과 (sandbox/skill-loop-port)
- [ ] Phase 1 단위 1 — sandbox → engine 승격
- [ ] Phase 1 단위 2 — Anthropic provider adapter Port + mock 폐기

## 다음 액션

- [ ] Phase 1 단위들을 순차 진행 (`research/phase-1-todo.md` 참조)
- [ ] 각 단위 종료 시 차용 회고 한 문단 추가하여 다음 단위 계획에 반영
