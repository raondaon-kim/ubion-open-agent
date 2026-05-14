# Phase 0 Retrospective — 차용 가능성 검증

> v0.1에서는 "Hermes 가치 검증" 회고 템플릿이었음. v0.2에서 의제가 "차용 가능성 검증"으로 바뀌어 본 문서 전체를 재작성. PROJECT_SPEC v0.2 변경 이력 참조.

## 메타

- 담당자: ax 센터 + Claude (Opus 4.7)
- 작성일: 2026-05-13
- Phase 0 기간: 2026-05-13 (단일 세션 내 완수)
- Hermes 차용 기준 커밋: `b06e9993021a8eebd891fc60d52372446315b2f0`

## 1. 한 줄 결론

- **결론**: skill 자동 생성/큐레이션 루프(`agent/curator.py`) 차용 시범 성공. 진짜 LLM이 21초 동안 review를 수행하고 의도된 결과를 출력. 차용 비율 85%, 코드 수정 0줄, lazy import 5개 모두 자동 해결.
- **추천 판정**: 🟢 **GREEN** — Phase 1 진행

## 2. 차용 시범 정량 요약

| 항목 | 값 |
|------|---|
| 차용 대상 모듈 | `agent/curator.py` (1,781 라인) + 의존성 |
| 차용 강도 | Vendor copy (curator.py, skill_usage.py), Port (agent_home.py) |
| 작업 위치 | `sandbox/skill-loop-port/` |
| 차용된 Hermes 코드 줄 수 | 2,421 라인 (헤더 +31라인 = +1.3%) |
| 새로 작성한 글루 코드 | 약 420 라인 (shim 3개 + Mock + run_demo) |
| 차용 비율 (vendored / total) | 85% |
| 미해결 의존성 | 0 |
| 작업 시간 | 약 50분 |
| End-to-end LLM 1회 호출 | 21.16초, 약 $0.40 (Opus 4.7) |
| Vendored 파일에 가해진 수정 | 0줄 (라이선스 헤더 prepend 외) |

상세는 [`skill-loop-port-feasibility.md §5`](skill-loop-port-feasibility.md) 참조.

## 3. 변형 실험 결과

| 시나리오 | 결과 |
|---------|------|
| 정상 fixtures (5 skills) — dry-run | 🟢 성공. 2 클러스터 정확 식별, REPORT.md/run.json 정상 생성 |
| 빈 fixtures (0 skills) | 🟢 LLM 호출 없이 `skipped (no candidates)`로 종료. 비용 0 |
| `set_paused(True)` | 🟢 `should_run_now=False`, `maybe_run_curator` returns None |

## 4. 차용 방법론 검증 — 일반화 가능성

본 시범에서 검증된 **"vendor copy + shim 패턴"**:

1. 원본 Hermes 코드를 한 글자도 안 바꿈 (라이선스 헤더 prepend만)
2. 원본이 expecting하는 모듈 이름(`hermes_constants`, `tools`)을 같은 이름의 shim 파일로 제공
3. lazy import 처리:
   - 원본이 `try/except`로 감싼 부분 (3개) → 우리 환경에 없으면 자동 fallthrough
   - 명시적 대체 필요한 부분 (`run_agent.AIAgent`) → 1개 shim
   - 같은 모듈 alias import (`tools import skill_usage as _u`) → 자동 해소
4. provenance 데이터 형식 (`.usage.json`)도 그대로 호환

이 패턴이 [`hermes-code-walkthrough.md`](hermes-code-walkthrough.md) §3.1의 다른 Vendor copy 대상 모듈에도 일반화되리라 추정. 검증은 Phase 1 첫 차용 작업에서.

## 5. 비용 시뮬레이션

| 시나리오 | Opus 4.7 | Sonnet 4.6 |
|---------|---------|----------|
| 5 skills, 1회 dry-run | $0.40 | ~$0.05 |
| 50명 × 주 1회 × 4주 = 월 200회 | ~$80 | ~$10 |
| 100 skills, 1회 (prompt 80KB) | $4 | $0.5 |

100 skills 규모에 도달하면 `_render_candidate_list` 형식 최적화 또는 Sonnet 라우팅 검토 필요. Phase 3 이슈로 기록.

## 6. 사내 보안 정책 (병행 조사) — 부분 진행

본 회고일까지 [`security-policy-check.md`](security-policy-check.md) 미답변. Phase 1 시작 전에 완료 필요. **Phase 1 진입 자체에는 게이트 영향 없음** (Phase 1은 PoC, 실사용자 2명 = ax 센터 + 동료).

## 7. 치명적 블로커

| 블로커 후보 | 상태 |
|------------|------|
| Hermes 외부 진입점 부재 | 🟢 해소됨 (`hermes-message-interface.md` 완료, 본 차용 검증과 무관) |
| 차용 코드 떼어내기 비현실적 | 🟢 해소됨 (본 시범에서 직접 입증) |
| LLM 비용 폭주 | 🟢 통제 가능 — 호출당 $0.40, 월 시뮬레이션 적정 |
| 사내 보안 정책 충돌 | 🟡 미답변. Phase 1 시작 전 완료 |
| Hermes 자기진화 품질 불안정 | 🟢 본 시범에서 클러스터링 + 통합 전략 정확. 본 격적 가치는 Phase 1+ 실사용 데이터로 추가 검증 |

## 8. Phase Gate 판정

- [x] **🟢 GREEN**
  - 차용 시범 성공: end-to-end LLM 호출, REPORT.md 정상 생성
  - 의존성 절단이 예상보다 쉬움 (lazy import 자동 처리)
  - 차용 비율 85% — 실제로 *우리가 새로 짠 코드는 글루뿐*
  - LLM이 curator 프롬프트 노하우를 정확히 실행 → 자기진화의 *지능*이 코드 분리 가능함을 입증
  - 비용 예측 가능
  - → **Phase 1 진행**

- [ ] 🟡 YELLOW: 해당 없음
- [ ] 🔴 RED: 해당 없음

## 9. Phase 1 진입 전 보완할 일

1. [`security-policy-check.md`](security-policy-check.md) 사내 보안팀 1차 답변 받기
2. Phase 1 진입 시 sandbox → `engine/` 승격 정리
   - `sandbox/skill-loop-port/curator.py` → `engine/learning/curator.py`
   - shim 파일들은 `engine/` 모듈 구조에 흡수
   - Mock AIAgent는 실제 LLM client adapter로 대체
3. [`phase-1-todo.md`](phase-1-todo.md) 옵션 C 반영하여 갱신 (지금까지는 v0.1 가정 기반)
4. 모델 ID 카탈로그 (`claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001` 등 정확한 ID 정리)
5. Windows UTF-8 stdio 처리 (`hermes_bootstrap.py` Vendor copy 후보)

## 10. 다음 액션

- 바로 할 일: PROJECT_SPEC §7 결정 매트릭스에 "Phase 0 게이트 = GREEN" 기록, `.phase` 파일을 `1`로 전환할 시점 결정
- 보류할 일: 사내 보안팀 회신 전까지는 `.phase` 전환 대기 권장
- Phase 1 진입 전: §9 보완 작업

## 11. 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-13 | 초안 (v0.1 가치 검증용) |
| 2026-05-13 | **전면 재작성** — v0.2 차용 가능성 검증 의제 반영, GREEN 판정 기록 |
