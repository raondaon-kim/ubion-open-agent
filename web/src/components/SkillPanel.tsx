import { useState } from "react";

/**
 * Stage 4 — Skill 패널.
 *
 * Phase 1 (B) 시점에 백엔드는 skill_view / skill_manage 를 *tool* 로만
 * 노출함 (LLM 이 호출). 사용자가 *직접* 브라우저에서 skill 목록을
 * 조회하려면 단위 10 server 에 별도 REST endpoint 가 필요:
 *
 *     GET    /ubion/skills              → list
 *     GET    /ubion/skills/{name}       → SKILL.md body
 *     POST   /ubion/skills              → create
 *     PATCH  /ubion/skills/{name}       → edit
 *     DELETE /ubion/skills/{name}       → archive
 *
 * 이 endpoint 들은 단위 12 의 *v2* 작업으로 분리 — 현재는 사용자 입력
 * 그대로 표시하는 read-only placeholder.
 */
export function SkillPanel() {
  const [hover, setHover] = useState<string | null>(null);

  return (
    <div className="flex-1 overflow-y-auto pl-14 pr-3 sm:pl-6 sm:pr-6 py-6">
      <div className="max-w-3xl mx-auto">
        <header className="mb-6">
          <h2 className="text-2xl font-medium tracking-tight">스킬</h2>
          <p
            className="text-sm mt-1"
            style={{ color: "var(--color-text-muted)" }}
          >
            에이전트가 학습한 절차적 기억 (
            <code>~/.ubion-agent/skills/</code>). 자동 생성된 스킬과 직접 작성한
            스킬이 함께 표시됩니다.
          </p>
        </header>

        {/* TODO endpoint 가 준비되면 fetchSkills() 로 교체 */}
        <div
          className="rounded-xl border p-6 text-sm"
          style={{
            background: "var(--color-bg-card)",
            borderColor: "var(--color-border)",
            color: "var(--color-text-muted)",
          }}
        >
          <p className="mb-3">
            현재 백엔드는 스킬 CRUD 를 <em>LLM tool</em> (
            <code>skill_view</code>, <code>skill_manage</code>) 로만 노출합니다.
          </p>
          <p>
            브라우저에서 스킬을 직접 보거나 편집하려면 단위 10 API 서버에 다음
            엔드포인트 추가가 필요합니다 — 단위 12 v2 작업:
          </p>
          <ul className="mt-3 space-y-1.5 font-mono text-xs">
            {[
              "GET    /ubion/skills",
              "GET    /ubion/skills/{name}",
              "POST   /ubion/skills",
              "PATCH  /ubion/skills/{name}",
              "DELETE /ubion/skills/{name}",
            ].map((line) => (
              <li
                key={line}
                onMouseEnter={() => setHover(line)}
                onMouseLeave={() => setHover(null)}
                style={{
                  color:
                    hover === line
                      ? "var(--color-text)"
                      : "var(--color-text-muted)",
                }}
              >
                {line}
              </li>
            ))}
          </ul>
        </div>

        <p
          className="text-xs mt-4"
          style={{ color: "var(--color-text-dim)" }}
        >
          힌트: Phase 1 (B) 시 에이전트 1주 시나리오에서는 대화 안에서 “스킬로
          저장해줘” 같은 자연어 명령으로 충분합니다 — 에이전트가{" "}
          <code>skill_manage</code> 를 자동 호출.
        </p>
      </div>
    </div>
  );
}
