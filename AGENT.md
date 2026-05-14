# AGENT.md — Claude Code 작업 가이드

> **이 파일은 Claude Code가 본 프로젝트를 다룰 때 매번 가장 먼저 읽는 컨텍스트 파일입니다.**
> 환경 독립적으로 작성되었으며, Claude Code, Codex, Cursor 등 어느 coding agent에서도 동일하게 동작해야 합니다.

---

## 프로젝트 정체성

**Self-Evolving Agent Platform** — 사내 멀티테넌트 자기진화 에이전트 호스팅 플랫폼.

상세 명세는 **`PROJECT_SPEC.md`**를 참조. 본 파일은 *작업 방식*에 대한 가이드.

---

## 작업 원칙

### 1. SPEC-FIRST

- 코드 작성 전 항상 `PROJECT_SPEC.md`를 읽고 현재 Phase와 작업 범위를 확인할 것.
- 새로운 결정이 발생하면 `PROJECT_SPEC.md`의 섹션 7 (결정 매트릭스)을 업데이트할 것.
- 사용자가 "그냥 짜봐"라고 해도 SPEC에 없는 것이면 *"SPEC에 명시되지 않은 결정입니다. 먼저 SPEC에 추가하시겠습니까?"* 라고 되물을 것.

### 2. PHASE GATE 존중

- 현재 Phase가 무엇인지 항상 확인할 것 (저장소 루트의 `.phase` 파일 또는 PROJECT_SPEC 섹션 4 참조).
- **Phase 0 검증 게이트 통과 전에는 인프라 코드 작성 금지.** 조사와 직접 사용만.
- Phase가 끝났는지 사용자에게 확인하지 않고 다음 Phase 작업을 시작하지 말 것.

### 3. 조사 결과는 markdown으로 남긴다

- `research/` 디렉터리에 조사 항목별로 파일 생성.
- 형식: 질문 → 조사 방법 → 결과 → 결론 → 후속 액션.
- 결론이 SPEC의 결정에 영향을 주면 SPEC을 업데이트.

### 4. SMALL UNITS

- Claude Code에 한 번에 위임할 작업 단위는 다음 중 하나여야 함:
  - 조사 1건
  - 컴포넌트 1개의 PoC
  - 명세 문서 1개 작성
- "Phase 1 전체를 짜줘" 같은 큰 위임은 거부할 것.

### 5. NO PREMATURE OPTIMIZATION

- Phase 1은 docker-compose, JSON 파일 매핑, 단순 password auth로 충분.
- Phase 3에서 사용자 수를 보고 K8s/SSO/모니터링 도입.
- 처음부터 K8s/Terraform/Helm을 짜지 말 것.

---

## 디렉터리 구조

```
project-root/
├── AGENT.md                  ← 이 파일
├── PROJECT_SPEC.md           ← 상세 명세서 (진실의 원천)
├── .phase                    ← 현재 Phase 마커 (예: "0", "1", "2")
├── .hermes-clone/            ← Hermes 저장소 shallow clone (read-only reference, 차용 원천. git ignore)
├── research/                 ← 조사 결과
├── sandbox/                  ← Phase 0 차용 시범 작업 격리 디렉터리
│   └── skill-loop-port/      ← 첫 시범: skill 자동 생성 루프 포팅
├── engine/                   ← Phase 1+ 자체 에이전트 엔진 (sandbox 승격분 + 신규 작성)
├── docs/                     ← Phase 2 산출 정책 문서들
├── infra/                    ← Phase 1+ 인프라 코드
├── web-ui/                   ← 채팅 UI
├── dispatcher/               ← 라우터 서비스
├── agent-container/          ← 컨테이너 정의 (engine + entrypoint)
└── skills-public/            ← 공용 skill repo (별도 git submodule)
```

---

## 코딩 컨벤션

### 언어 선택 (Phase 1 시작 시 확정)

- **Web UI**: Next.js (TypeScript) — ax 센터 익숙한 스택
- **Dispatcher**: 미정 (Node.js Express, Python FastAPI, Go 중)
- **Hermes container entrypoint**: Bash + Python (Hermes가 Python 기반)

### 스타일

- TypeScript: strict mode, ESLint + Prettier
- Python: ruff, type hints
- Bash: `set -euo pipefail` 기본

### 커밋 메시지

- Conventional Commits 형식: `feat:`, `fix:`, `docs:`, `chore:`, `research:`
- Phase 명시: `[Phase 1] feat: dispatcher initial implementation`

---

## 외부 의존성 정책

### 사용 결정된 것
- **Hermes Agent**: 의존성으로 박지 **않음**. **Reference codebase + 적극적 코드 차용 원천**으로만 사용. 차용 강도(Vendor copy / Port / Reference / Drop)는 모듈별로 다름 — `research/hermes-code-walkthrough.md` 참조. 업스트림 추적 안 함, 한 번 차용한 코드는 우리 자산.
- **Docker**: 최신 안정 버전
- **Python**: 엔진 구현 언어 (Hermes Port 비용 최소화)

### 사용 검토 중인 것
- Open WebUI, Keycloak, K8s — Phase 3 시점에 결정

### 사용 금지
- Slack/Telegram SDK (의도적 제외)
- 단일 공유 에이전트 패턴의 라이브러리 (이 프로젝트의 사상 반대)
- **Hermes를 pip/uv dependency로 박는 것**: 차용은 코드 복사로, import는 우리 모듈 경로만 사용

### Hermes 차용 작업 시 준수 사항
- 차용된 모든 파일 상단에 MIT 라이선스 헤더 + 출처 명시 (`research/hermes-license-policy.md` 템플릿 사용)
- 차용 시범 단계의 코드는 `sandbox/<topic>/` 아래에 격리. Phase 게이트 통과 후 `engine/`으로 승격
- 차용 후 Hermes의 후속 변경은 자동 반영되지 않음을 인지 — 버그 수정도 우리 코드에서 직접

---

## 보안 원칙 (작업 중에도 적용)

- LLM API 키는 `.env`에만, 절대 커밋 금지.
- Hermes 컨테이너는 사용자별 격리 — 한 컨테이너가 다른 사용자 볼륨에 접근 가능한 코드 작성 금지.
- bash 실행 권한이 있는 시스템임을 항상 인지. 권한 escalation 가능한 코드 패턴 회피.

---

## 자주 하는 질문 (Claude Code 대답용)

**Q: 지금 어떤 Phase야?**
A: `.phase` 파일을 읽거나 사용자에게 확인. 모르면 작업 시작 안 함.

**Q: 새 기능 추가해줘.**
A: PROJECT_SPEC.md 어느 섹션의 결정인지 먼저 확인. 없으면 SPEC 추가 제안.

**Q: 이거 빠르게 짜줘.**
A: Phase와 SPEC 확인 → 작업 단위 분할 → 사용자 확인 → 실행.

**Q: 테스트는?**
A: Phase 1 PoC 코드도 핵심 로직(격리, 라우팅, sync)에는 통합 테스트 필수. UI 컴포넌트는 Phase 3까지 단위 테스트 면제.

---

## 참고 프로젝트 (상세는 PROJECT_SPEC.md 섹션 6)

- **Hermes Agent**: https://github.com/NousResearch/hermes-agent — 핵심 엔진
- **OpenClaw**: https://github.com/openclaw/openclaw — 컨벤션 reference
- **DeerFlow**: https://github.com/bytedance/deer-flow — 하네스 아키텍처 reference
- **Open WebUI**: https://github.com/open-webui/open-webui — UI 후보

---

## 이 파일의 변경

이 파일은 Phase 전환 시 또는 작업 원칙이 변경될 때만 수정. 일상 작업 결정은 PROJECT_SPEC.md에 기록.

*끝.*
