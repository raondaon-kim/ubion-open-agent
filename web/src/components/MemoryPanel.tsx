/**
 * Stage 5 — Memory 패널.
 *
 * 단위 6 의 memory_manager 는 *provider 등록* 위에 동작.
 * 사용자가 메모리를 직접 보거나 편집하려면 단위 10 server 에 다음
 * endpoint 추가가 필요 (단위 12 v2):
 *
 *     GET    /ubion/memory             → 모든 provider 의 system_prompt_block 합
 *     POST   /ubion/memory             → 항목 추가
 *     DELETE /ubion/memory/{id}        → 항목 제거
 *
 * 현재는 invariant ("메모리가 없어도 에러 없음") 설명 + 향후 endpoint 시드.
 */
export function MemoryPanel() {
  return (
    <div className="flex-1 overflow-y-auto pl-14 pr-3 sm:pl-6 sm:pr-6 py-6">
      <div className="max-w-3xl mx-auto">
        <header className="mb-6">
          <h2 className="text-2xl font-medium tracking-tight">메모리</h2>
          <p
            className="text-sm mt-1"
            style={{ color: "var(--color-text-muted)" }}
          >
            에이전트가 누적한 사용자 정보·피드백·프로젝트 맥락. 메모리가 비어
            있어도 대화는 정상 동작합니다.
          </p>
        </header>

        <div
          className="rounded-xl border p-6 text-sm"
          style={{
            background: "var(--color-bg-card)",
            borderColor: "var(--color-border)",
            color: "var(--color-text-muted)",
          }}
        >
          <p className="mb-3">
            현재 메모리는 LLM 의 <code>memory</code> 도구로만 갱신됩니다 —
            에이전트가 대화 도중 자동으로 저장.
          </p>
          <p>
            브라우저에서 메모리를 직접 보거나 편집하려면 단위 10 서버에 다음
            엔드포인트 추가 — 단위 12 v2 작업:
          </p>
          <ul className="mt-3 space-y-1.5 font-mono text-xs">
            {[
              "GET    /ubion/memory",
              "POST   /ubion/memory",
              "DELETE /ubion/memory/{id}",
            ].map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>

        <p
          className="text-xs mt-4"
          style={{ color: "var(--color-text-dim)" }}
        >
          힌트: 시 에이전트와의 1주 시나리오에서는 “지금 한 말 기억해줘” 같은
          자연어 명령으로 충분 — 에이전트가 <code>memory</code> 도구 자동 호출.
        </p>
      </div>
    </div>
  );
}
