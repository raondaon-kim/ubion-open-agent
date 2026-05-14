import { useEffect, useState } from "react";
import { fetchDebugInfo, fetchDebugLog, type DebugInfo } from "../api/client";
import type { ProgressEvent } from "../api/client";

/**
 * 개발자/사용자 디버그 패널. Ctrl+Shift+D 로 토글.
 *
 * 두 가지를 한 화면에 띄운다:
 *   1. 백엔드 상태 (agent_home, 키 존재 여부, idle timeout, 로그 경로)
 *   2. 최근 SSE 이벤트 ring buffer — `App.tsx` 가 `useDebugEvents` 로
 *      append, 여기서 그 배열을 읽어 시간순으로 표시.
 *
 * 설치본에서도 동작하는 게 핵심 — Tauri DevTools 가 production 빌드에
 * 닫혀 있을 때 사용자가 "왜 멈췄지?" 를 스스로 추적할 수 있게 한다.
 */
export interface DebugEvent {
  ts: number;
  kind: "request" | "progress" | "delta" | "error" | "system";
  text: string;
  detail?: unknown;
}

export function DebugDrawer({
  open,
  onClose,
  events,
  onClear,
}: {
  open: boolean;
  onClose: () => void;
  events: DebugEvent[];
  onClear: () => void;
}) {
  const [info, setInfo] = useState<DebugInfo | null>(null);
  const [log, setLog] = useState<{ path: string; lines: string[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setErr(null);
    try {
      const [i, l] = await Promise.all([fetchDebugInfo(), fetchDebugLog(150)]);
      setInfo(i);
      setLog(l);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  // open 이 true 로 바뀔 때마다 한 번 갱신
  useEffect(() => {
    if (open) refresh();
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-y-0 right-0 z-50 w-[min(560px,90vw)] flex flex-col border-l shadow-2xl"
      style={{
        background: "var(--color-bg)",
        borderColor: "var(--color-border)",
        color: "var(--color-text)",
      }}
    >
      <header
        className="flex items-center gap-2 px-4 h-12 border-b"
        style={{ borderColor: "var(--color-border)" }}
      >
        <span className="text-sm font-medium">디버그</span>
        <span
          className="text-xs"
          style={{ color: "var(--color-text-dim)" }}
        >
          Ctrl+Shift+D
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="px-2 py-1 text-xs rounded-md"
            style={{ background: "var(--color-bg-hover)" }}
          >
            {loading ? "로드 중…" : "새로고침"}
          </button>
          <button
            type="button"
            onClick={onClear}
            className="px-2 py-1 text-xs rounded-md"
            style={{ background: "var(--color-bg-hover)" }}
            title="브라우저 이벤트 버퍼만 비웁니다 (서버 로그는 보존)"
          >
            버퍼 지우기
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="w-7 h-7 rounded-md text-sm"
            style={{ color: "var(--color-text-muted)" }}
          >
            ✕
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {err && (
          <div
            className="text-sm px-3 py-2 rounded-md"
            style={{ background: "rgba(220,40,40,0.12)", color: "#e88" }}
          >
            {err}
          </div>
        )}

        <Section title="백엔드 상태">
          {info ? (
            <dl className="text-xs space-y-1 font-mono">
              <Row k="agent_home" v={info.agent_home} />
              <Row k="workspace" v={info.workspace} />
              <Row k="log_file" v={info.log_file} />
              <Row k="SOUL.md" v={info.soul_md_exists ? "exists" : "MISSING"} />
              <Row k="USER.md" v={info.user_md_exists ? "exists" : "MISSING"} />
              <Row k="DEEPSEEK_API_KEY" v={info.deepseek_key_set ? "set" : "NOT SET"} />
              <Row k="ANTHROPIC_API_KEY" v={info.anthropic_key_set ? "set" : "NOT SET"} />
              <Row k="idle_timeout_s" v={String(info.idle_timeout_s)} />
            </dl>
          ) : (
            <div className="text-xs" style={{ color: "var(--color-text-dim)" }}>
              로드 안 됨
            </div>
          )}
        </Section>

        <Section title={`최근 클라이언트 이벤트 (${events.length})`}>
          {events.length === 0 ? (
            <div className="text-xs" style={{ color: "var(--color-text-dim)" }}>
              아직 이벤트가 없습니다. 메시지를 보내면 여기에 쌓입니다.
            </div>
          ) : (
            <ul className="text-xs font-mono space-y-0.5 max-h-72 overflow-y-auto">
              {events.slice(-200).map((e, i) => (
                <li key={i} className="flex gap-2">
                  <span style={{ color: "var(--color-text-dim)" }}>
                    {new Date(e.ts).toLocaleTimeString()}
                  </span>
                  <span
                    className="px-1.5 rounded"
                    style={{
                      background: "var(--color-bg-hover)",
                      color: "var(--color-text-muted)",
                      minWidth: "4.5rem",
                      textAlign: "center",
                    }}
                  >
                    {e.kind}
                  </span>
                  <span className="whitespace-pre-wrap break-all">{e.text}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={`서버 로그 (${log?.lines.length ?? 0} 줄)`}>
          {log && log.lines.length > 0 ? (
            <pre
              className="text-[11px] font-mono whitespace-pre-wrap max-h-96 overflow-y-auto px-2 py-2 rounded"
              style={{ background: "var(--color-bg-card)" }}
            >
              {log.lines.join("\n")}
            </pre>
          ) : (
            <div className="text-xs" style={{ color: "var(--color-text-dim)" }}>
              아직 기록 없음 ({log?.path ?? "?"})
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3
        className="text-xs uppercase tracking-wider mb-1.5"
        style={{ color: "var(--color-text-dim)" }}
      >
        {title}
      </h3>
      {children}
    </section>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  const bad = v === "MISSING" || v === "NOT SET";
  return (
    <div className="flex gap-2">
      <dt
        className="shrink-0"
        style={{ color: "var(--color-text-muted)", minWidth: "9.5rem" }}
      >
        {k}
      </dt>
      <dd className="break-all" style={{ color: bad ? "#e88" : "var(--color-text)" }}>
        {v}
      </dd>
    </div>
  );
}

/**
 * 외부 호출자(`App.tsx`)가 ProgressEvent / 일반 텍스트를 append 할 때
 * 쓰는 헬퍼. ring buffer (최대 500개) 로 유지해 메모리 폭주 방지.
 */
export function appendDebug(
  setEvents: (updater: (prev: DebugEvent[]) => DebugEvent[]) => void,
  ev: Omit<DebugEvent, "ts"> & { ts?: number },
): void {
  setEvents((prev) => {
    const next = [...prev, { ts: ev.ts ?? Date.now(), kind: ev.kind, text: ev.text, detail: ev.detail }];
    if (next.length > 500) next.splice(0, next.length - 500);
    return next;
  });
}

export function formatProgressForDebug(ev: ProgressEvent): string {
  if (ev.stage === "tool") return `tool start: ${ev.toolName ?? "?"}`;
  if (ev.stage === "tool_done") return `tool done: ${ev.toolName ?? "?"} (${ev.ok ? "ok" : "FAIL"})`;
  return `thinking (turn ${ev.turn ?? 1})`;
}
