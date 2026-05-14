# Phase 1 (B) 시 에이전트 1주 시나리오 — 운영 가이드

> 이 문서는 *매일 보면서 진행* 하는 실무 가이드입니다. 시나리오 정의·게이트는
> [`phase-1-demo-scenario-poet.md`](phase-1-demo-scenario-poet.md) 참조.

작성: 2026-05-14 (D-단계 진입 직전)
검증자: ax 센터 1인

---

## 0. 진입 전 체크리스트 (Day 0 — 한 번만)

| 항목 | 상태 |
|------|------|
| 단위 1~13 종료 | ✅ |
| Phase 1 가벼움 부채 (B-1/B-2/B-3) 완료 | ✅ (lazy import + bundled_skills 분리 + 스킬 인덱스 캐시) |
| `engine/bundled_skills/` → `skills-bundle/` 이동 검증 | ✅ |
| FastAPI 9000 + Vite 8803 부팅 검증 | ✅ |
| `.env` 에 `ANTHROPIC_API_KEY` 설정 | □ 사용자 확인 필요 |
| `~/.ubion-agent/` 초기 상태 결정 (빈 상태 vs 기존 보존) | □ §1 참조 |
| 시 작업 폴더 (`UBION_WORKSPACE`) 결정 | □ §2 참조 |
| 사전 LLM 비용 상한 결정 | □ §3 참조 |

---

## 1. agent_home 초기화 결정

**기본 위치**: `C:\Users\<당신>\.ubion-agent\`

선택지:
- **(a) 빈 상태로 시작 (추천)** — 자기진화를 처음부터 관찰. 다만 86개 bundled skill 은 자동 시드됨 (그건 의도된 출발선)
- **(b) 지금까지 누적된 상태 그대로** — 기존 SKILL.md / 메모리 보존. 시 시나리오에선 처음 시작이 깔끔함

**(a) 선택 시 명령**:
```powershell
# Powershell — 안전 백업 후 초기화
$home_dir = "$env:USERPROFILE\.ubion-agent"
if (Test-Path $home_dir) {
    $backup = "$env:USERPROFILE\.ubion-agent.backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Move-Item $home_dir $backup
    Write-Output "기존 → $backup 로 백업"
}
```

다음 부팅 시 자동으로 빈 `~/.ubion-agent/` 가 만들어지고 `skills-bundle/` 가 시드됩니다.

---

## 2. 워크스페이스 (`UBION_WORKSPACE`) 준비

시 창작 결과물이 모일 폴더입니다. **새 파일만 생성 가능 (수정/삭제 금지)** 정책이 자동 적용됩니다.

```powershell
# 예: D:\poems\classical
$workspace = "D:\poems\classical"
New-Item -ItemType Directory -Path $workspace -Force | Out-Null
$env:UBION_WORKSPACE = $workspace
# .env 에도 추가하면 다음 부팅 시 자동 적용
Add-Content -Path "D:\Self-Evolving Agent Platform\.env" -Value "UBION_WORKSPACE=$workspace"
```

워크스페이스 안에 미리 둘 만한 자료:
- `references/` — 좋아하는 시인의 시집 본문 (저작권 유의)
- `drafts/` — 진행 중 작품 초안
- `notes.md` — 시 톤·표현 메모

에이전트는 이 폴더의 파일을 *읽을 수 있지만 수정·삭제는 못함*. 새 작품은 같은 폴더에 새 파일로 추가됩니다 (`create_workspace_file` 도구).

---

## 3. LLM 비용 상한 결정 (Phase 1 GREEN 게이트 항목)

| 모델 | 1턴 평균 비용 (입력 5K + 출력 1K) | 1주 누적 추정 (40세션 × 8턴) |
|------|----------------------------|----------------------------|
| Claude Opus 4.7 | ~$0.16 | ~$50 |
| Claude Sonnet 4.6 | ~$0.05 | ~$15 |
| DeepSeek v4-flash | ~$0.005 | ~$1.5 |

**권장 상한**: $30 (혼합 사용, 주력 Sonnet + 어려운 결정 시 Opus)

매일 끝에 측정 — Anthropic 콘솔의 Usage 페이지 또는 응답의 `usage` 필드 합산.

---

## 4. Day 0 — SOUL.md / USER.md 작성

### SOUL.md 초안

`~/.ubion-agent/SOUL.md` 에 시 에이전트의 정체성을 정의합니다. 시나리오에선 *처음 한 번만* 작성하고 그 후엔 에이전트가 자기 USER.md / MEMORY.md 로 보강.

예시 (그대로 써도 되고 다듬어도 됨):

```markdown
# SOUL — 시 동반자

나는 당신과 함께 시를 쓰는 동반자입니다.

## 정체성
- 당신의 취향을 학습하면서 시를 짓고 다듬는 데 도움을 줍니다
- 답을 강요하지 않습니다. 여러 선택지를 제시하고 당신이 고르게 합니다
- 첫 줄부터 완성된 시를 내놓기보다, 시상 → 거친 초안 → 다듬기의 단계를 함께 갑니다

## 작업 원칙
- 새 시를 만들 때는 `create_workspace_file` 로 워크스페이스에 markdown 파일로 저장합니다
- 사용자의 피드백 ("이 표현 좋다", "이 부분 진부하다") 은 `memory` 도구로 USER.md / MEMORY.md 에 기록합니다
- 반복되는 패턴 (선호 형식, 자주 쓰는 단어 회피 등) 은 `skill_manage` 로 자동 skill 을 만들어 다음 작업에 적용합니다

## 금지
- 사용자가 명시적으로 요청하지 않은 한 *기존 워크스페이스 파일을 수정하려 시도하지 않습니다* (정책상 차단되어 있지만 사용자 의도와도 일치)
- 시의 "정답" 을 단정하지 않습니다 — 시는 선택의 예술
```

### USER.md 초안

`~/.ubion-agent/USER.md` 에 *당신* 에 대한 컨텍스트:

```markdown
# USER — ax 센터 김용현

## 역할
- Ubion ax 센터 책임자. 자기진화 에이전트 플랫폼 (이 프로젝트) 의 주 검증자

## 시 취향 (시작점 — 시간이 가면서 에이전트가 갱신)
- (여기에 좋아하는 시인 / 자주 쓰는 형식 / 피하고 싶은 클리셰 등을 *3-5줄만* 적습니다. 너무 많이 적으면 학습 가치 없음)

## 작업 스타일
- 한 번에 완성보다 여러 번의 다듬기를 선호
- 한국어. 영어는 인용 / 참고 시만
```

USER.md 의 "시 취향" 부분은 *비워두거나 최소만* 적어주세요 — 에이전트가 1주 동안 *직접 학습해서 채우는* 것이 검증 게이트의 핵심.

---

## 5. 시작 절차 (Day 0 마무리)

```powershell
# 1) 백업 (만일을 위해)
$src = "$env:USERPROFILE\.ubion-agent"
if (Test-Path $src) {
    Set-Location $src
    git init 2>$null
    git add .
    git commit -m "scenario-start" 2>$null
    Set-Location 'D:\Self-Evolving Agent Platform'
    Write-Output "git scenario-start 저장됨"
}

# 2) 서버 부팅
$env:PYTHONUTF8 = '1'
python -m engine.server  # 백그라운드 또는 별도 콘솔

# 3) 다른 콘솔에서 Vite 부팅
Set-Location 'D:\Self-Evolving Agent Platform\web'
npm run dev

# 4) 브라우저에서 http://localhost:8803/
```

---

## 6. 매일 운영 (Day 1–7)

### 세션 시작
1. 서버 두 개 (FastAPI 9000 / Vite 8803) 살아있는지 확인
2. 브라우저에서 채팅 화면 진입 — 어제의 대화는 *세션 히스토리* 에 있지만 새 세션은 깨끗하게 시작
3. 어제 USER.md / MEMORY.md 에 무엇이 쌓였는지 *부담 없이* 확인 (에이전트가 알아서 system prompt 에 주입함)

### 한 세션 안에서 하는 일 (자유 혼합)
- 새 시 한 편 부탁
- 기존 초안 다듬기
- 시상 brainstorming
- 결과물 피드백 ("이 표현 좋다" / "이 부분 진부하다")
- 가끔 *명시적인* 질문: "내가 어떤 표현을 자주 쓰는지 기억해?"

### 세션 종료 시 (3분)
1. `git -C ~/.ubion-agent status` — 어떤 파일이 변경됐는지 확인
2. 새 skill 생긴 것 있나? `ls ~/.ubion-agent/skills/custom/` 확인
   - 매 세션 응답 종료 직후 백그라운드 curator 가 자동 호출됨 (B-5).
   - 게이트 조건 (`should_run_now()`) 통과 시 새 SKILL.md 가 `skills/custom/` 또는 기존 스킬에 patch 형태로 들어옴.
3. **`research/phase-1-poet-usage-log.md` 에 한 줄 추가**:
   ```
   ## Day N (2026-05-XX)
   - 세션 수: X / 턴 수: X
   - 결과물 사용 여부: y/n
   - 사람 수정량 (0-10): X
   - 새 skill: <이름>
   - LLM 비용: $X.XX
   - 메모: <기억할 만한 사례 / 잘못 기억한 사례>
   ```
4. `git -C ~/.ubion-agent add . && git -C ~/.ubion-agent commit -m "day-N"`

---

## 7. 사고 발생 시

| 증상 | 대응 |
|------|------|
| 에이전트가 잘못된 skill 을 만듦 | `~/.ubion-agent/skills/custom/<이름>` 폴더 삭제 또는 SKILL.md frontmatter 의 `enabled: false` 설정 |
| 메모리가 엉뚱한 사실로 오염 | `~/.ubion-agent/MEMORY.md` 직접 편집 (또는 채팅으로 `memory remove` 도구 호출 요청) |
| 어제 상태로 되돌리고 싶음 | `cd ~/.ubion-agent && git log` 로 commit 찾고 `git reset --hard <day-N>` |
| 처음부터 다시 시작하고 싶음 | `git reset --hard scenario-start` |

---

## 8. 1주 후 (Day 7+ 회고)

1. `research/phase-1-poet-usage-log.md` 전체 검토
2. 자동 생성된 skill 목록 + 사람 평가 → `research/phase-1-poet-skills-snapshot.md`
3. `git -C ~/.ubion-agent log --oneline` 으로 시간순 변화 추적
4. 게이트 판정:
   - 자동 skill ≥ 3개 ✓?
   - 이전 세션 결정 반영 사례 ≥ 2회 ✓?
   - 같은 작업 반복 시 사람 수정량 감소 추세 ✓?
   - 1주 LLM 비용 ≤ 상한 ✓?
   - 부적절한 skill / 잘못 기억 ≤ 2회 ✓?
5. `research/phase-1-retrospective.md` 작성
6. 모두 ✓ → **Phase 1 GREEN** → Phase 2 (정책 문서) 진입
7. 일부 부분 실패 → Phase 1.5 보완 작업 정의 후 재진입

---

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-14 | 초안. D-단계 진입 직전. v0.4 정합 |
