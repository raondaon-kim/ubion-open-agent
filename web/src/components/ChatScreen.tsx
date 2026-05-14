import { useEffect, useRef, useState } from "react";
import { useTheme } from "../hooks/useTheme";
import {
  type ConversationMeta,
  fetchModels,
  getConversation,
  saveConversation,
  streamChatCompletion,
} from "../api/client";
import type { Message, ModelInfo, Panel } from "../types";
import { SkillPanel } from "./SkillPanel";
import { MemoryPanel } from "./MemoryPanel";
import { SettingsPanel } from "./SettingsPanel";
import type { DebugEvent } from "./DebugDrawer";
import { formatProgressForDebug } from "./DebugDrawer";

interface Props {
  panel: Panel;
  currentId: string | null;
  onConversationSaved: (meta: ConversationMeta) => void;
  onDebugEvent: (ev: Omit<DebugEvent, "ts"> & { ts?: number }) => void;
  onToggleDebug: () => void;
}

const SUGGESTED = [
  { title: "오늘 떠오른 시상을 함께 다듬어줘", subtitle: "짧은 시 한 편으로 정리" },
  { title: "사용자의 취향을 알려줘", subtitle: "지금까지 학습한 메모리 요약" },
  { title: "비유를 다섯 개만 만들어줘", subtitle: "주제: 비 오는 도시" },
];

export function ChatScreen({ panel, currentId, onConversationSaved, onDebugEvent, onToggleDebug }: Props) {
  const { theme, toggle } = useTheme();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [model, setModel] = useState<string>("deepseek-v4-flash");
  const [workspace, setWorkspace] = useState<string>("");
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // 현재 대화의 created 타임스탬프 — save 시 보존해서 첫 생성 시각을 안 잃게.
  const [createdAt, setCreatedAt] = useState<string | null>(null);

  // 모델 목록 + 워크스페이스 초기 로딩
  useEffect(() => {
    fetchModels()
      .then((list) => {
        setModels(list);
        if (list.length > 0 && !list.find((m) => m.id === model)) {
          setModel(list[0].id);
        }
      })
      .catch(() => {
        // 서버가 아직 안 떠 있어도 UI 는 멈추지 않는다 — model selector 가
        // 빈 상태로 유지되고 사용자가 settings 에서 base URL 을 조정 가능.
      });
    setWorkspace(localStorage.getItem("ubion.workspace") ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 메시지 추가될 때마다 스크롤 하단으로
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  // currentId 가 바뀌면 해당 대화를 불러와 messages 로 끼워넣는다.
  // null 로 바뀌면 = "새 대화" — 화면을 빈 상태로 리셋.
  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!currentId) {
        setMessages([]);
        setCreatedAt(null);
        return;
      }
      try {
        const detail = await getConversation(currentId);
        if (cancelled) return;
        setMessages(
          detail.turns.map((t) => ({
            id: crypto.randomUUID(),
            role: t.role,
            content: t.content,
            createdAt: t.timestamp || detail.meta.updated,
          })),
        );
        setCreatedAt(detail.meta.created || null);
        if (detail.meta.model) setModel(detail.meta.model);
      } catch {
        if (!cancelled) {
          setMessages([]);
          setCreatedAt(null);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [currentId]);

  async function sendMessage(text: string) {
    if (!text.trim() || busy) return;
    setBusy(true);
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      createdAt: new Date().toISOString(),
    };
    const placeholder: Message = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
      streaming: true,
    };
    const next = [...messages, userMsg, placeholder];
    setMessages(next);
    setInput("");

    const abort = new AbortController();
    abortRef.current = abort;

    onDebugEvent({ kind: "request", text: `send → ${model} (${text.length} chars)` });
    try {
      await streamChatCompletion({
        model,
        messages: next
          .filter((m) => !m.streaming)
          .map((m) => ({ role: m.role, content: m.content })),
        signal: abort.signal,
        onDelta: (delta) => {
          // Debug: 첫 delta 시점만 별도 표시, 이후는 노이즈라 생략
          onDebugEvent({ kind: "delta", text: `+${delta.length} chars` });
          setMessages((prev) => {
            const copy = prev.slice();
            const last = copy[copy.length - 1];
            if (last && last.role === "assistant") {
              // 첫 텍스트 delta 가 도착했다면 progress 단계는 끝
              copy[copy.length - 1] = {
                ...last,
                content: last.content + delta,
                progress: undefined,
              };
            }
            return copy;
          });
        },
        onProgress: (event) => {
          onDebugEvent({ kind: "progress", text: formatProgressForDebug(event), detail: event });
          setMessages((prev) => {
            const copy = prev.slice();
            const last = copy[copy.length - 1];
            if (!last || last.role !== "assistant") return prev;
            const prevProgress = last.progress;
            const completed = prevProgress?.toolsCompleted ?? 0;
            if (event.stage === "thinking") {
              copy[copy.length - 1] = {
                ...last,
                progress: {
                  stage: "thinking",
                  startedAt: Date.now(),
                  toolsCompleted: completed,
                },
              };
            } else if (event.stage === "tool") {
              copy[copy.length - 1] = {
                ...last,
                progress: {
                  stage: "tool",
                  toolName: event.toolName,
                  startedAt: Date.now(),
                  toolsCompleted: completed,
                },
              };
            } else if (event.stage === "tool_done") {
              copy[copy.length - 1] = {
                ...last,
                progress: {
                  stage: "thinking",
                  startedAt: Date.now(),
                  toolsCompleted: completed + 1,
                },
              };
            }
            return copy;
          });
        },
      });
      let finalMessages: Message[] = [];
      setMessages((prev) => {
        const copy = prev.slice();
        const last = copy[copy.length - 1];
        if (last) copy[copy.length - 1] = { ...last, streaming: false, progress: undefined };
        finalMessages = copy;
        return copy;
      });
      // 턴이 끝났으니 즉시 영구 저장 (md 파일 덮어쓰기)
      try {
        const meta = await saveConversation({
          id: currentId,
          model,
          created: createdAt,
          messages: finalMessages
            .filter((m) => m.content.trim())
            .map((m) => ({ role: m.role, content: m.content })),
        });
        if (!createdAt) setCreatedAt(meta.created);
        onConversationSaved(meta);
      } catch {
        // 저장 실패는 대화 흐름을 막지 않는다 — 다음 턴에 다시 시도됨
      }
    } catch (err) {
      onDebugEvent({ kind: "error", text: (err as Error).message, detail: err });
      setMessages((prev) => {
        const copy = prev.slice();
        const last = copy[copy.length - 1];
        if (last && last.role === "assistant") {
          copy[copy.length - 1] = {
            ...last,
            content: last.content || `[오류] ${(err as Error).message}`,
            streaming: false,
            progress: undefined,
          };
        }
        return copy;
      });
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    sendMessage(input);
  }

  function handleStop() {
    abortRef.current?.abort();
  }

  if (panel === "skills") return <SkillPanel />;
  if (panel === "memory") return <MemoryPanel />;
  if (panel === "settings") return <SettingsPanel />;

  return (
    <>
      {/* 상단 바: 모델 선택 + 워크스페이스 표시 + 테마 토글
          모바일에선 왼쪽 햄버거 자리 (~52px) 확보. */}
      <header
        className="flex items-center gap-3 pl-14 pr-3 sm:pl-5 sm:pr-5 h-14 border-b"
        style={{ borderColor: "var(--color-border)" }}
      >
        <div className="flex items-center gap-2">
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="bg-transparent text-sm font-medium outline-none cursor-pointer pr-1"
            style={{ color: "var(--color-text)" }}
          >
            {models.length === 0 && <option value={model}>{model}</option>}
            {models.map((m) => (
              <option key={m.id} value={m.id} style={{ background: "var(--color-bg)" }}>
                {m.id}
              </option>
            ))}
          </select>
          <span
            className="text-xs px-1.5 py-0.5 rounded"
            style={{
              background: "var(--color-accent-bg)",
              color: "var(--color-accent)",
            }}
          >
            {models.find((m) => m.id === model)?.provider ?? "anthropic"}
          </span>
          {busy && (
            <span
              className="text-xs"
              style={{ color: "var(--color-text-dim)" }}
              title="작성 중인 응답은 이전 모델로 끝까지 마무리됩니다"
            >
              · 다음 메시지부터 적용
            </span>
          )}
        </div>

        {workspace && (
          <div className="flex items-center gap-1 text-xs" style={{ color: "var(--color-text-muted)" }}>
            <span>·</span>
            <span>작업 폴더: {workspace}</span>
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={onToggleDebug}
            className="w-8 h-8 rounded-md flex items-center justify-center text-sm"
            style={{ color: "var(--color-text-muted)" }}
            title="디버그 (Ctrl+Shift+D)"
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-hover)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          >
            ⚙
          </button>
          <button
            type="button"
            onClick={toggle}
            className="w-8 h-8 rounded-md flex items-center justify-center text-sm"
            style={{ color: "var(--color-text-muted)" }}
            title={theme === "dark" ? "라이트 모드" : "다크 모드"}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-hover)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          >
            {theme === "dark" ? "☀" : "☾"}
          </button>
        </div>
      </header>

      {/* 메시지 영역 또는 빈 상태 */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto"
      >
        {messages.length === 0 ? (
          <EmptyState model={model} onSuggested={(t) => sendMessage(t)} />
        ) : (
          <MessageList messages={messages} />
        )}
      </div>

      {/* 입력 박스 */}
      <form
        onSubmit={handleSubmit}
        className="px-3 sm:px-6 pb-4 sm:pb-6 pt-3"
      >
        <div
          className="mx-auto max-w-3xl rounded-2xl border p-3"
          style={{
            background: "var(--color-bg-input)",
            borderColor: "var(--color-border)",
          }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage(input);
              }
            }}
            placeholder="메시지를 입력하세요…"
            rows={1}
            className="w-full bg-transparent outline-none resize-none text-[15px] leading-relaxed py-1 px-1"
            style={{ color: "var(--color-text)" }}
          />
          <div className="flex items-center gap-2 mt-2">
            <button
              type="button"
              className="w-8 h-8 rounded-md flex items-center justify-center text-sm"
              style={{ color: "var(--color-text-muted)" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-hover)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              title="첨부 (예정)"
            >
              +
            </button>
            <div className="ml-auto flex items-center gap-2">
              {busy ? (
                <button
                  type="button"
                  onClick={handleStop}
                  className="px-3 py-1.5 rounded-md text-sm"
                  style={{ background: "var(--color-bg-hover)", color: "var(--color-text)" }}
                >
                  중지
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="px-3 py-1.5 rounded-md text-sm font-medium disabled:opacity-40 transition-opacity"
                  style={{ background: "var(--color-accent)", color: "white" }}
                >
                  전송
                </button>
              )}
            </div>
          </div>
        </div>
        <p
          className="text-center text-xs mt-2"
          style={{ color: "var(--color-text-dim)" }}
        >
          Enter 로 전송 · Shift+Enter 로 줄 바꿈
        </p>
      </form>
    </>
  );
}

function EmptyState({ model, onSuggested }: { model: string; onSuggested: (t: string) => void }) {
  return (
    <div className="h-full flex flex-col items-center justify-center px-4 sm:px-6 py-6">
      <div
        className="w-14 h-14 rounded-full flex items-center justify-center mb-4 text-xl font-semibold"
        style={{
          background: "var(--color-accent-bg)",
          color: "var(--color-accent)",
        }}
      >
        U
      </div>
      <h1 className="text-2xl sm:text-3xl font-medium tracking-tight mb-2 text-center break-all">{model}</h1>
      <p className="text-sm mb-10" style={{ color: "var(--color-text-muted)" }}>
        오늘은 어떻게 도와드릴까요?
      </p>

      <div className="w-full max-w-2xl">
        <div className="text-xs mb-3 flex items-center gap-1.5" style={{ color: "var(--color-text-dim)" }}>
          <span>⚡</span>
          <span>추천</span>
        </div>
        <div className="grid gap-2">
          {SUGGESTED.map((s) => (
            <button
              key={s.title}
              type="button"
              onClick={() => onSuggested(s.title)}
              className="text-left px-4 py-3 rounded-xl border transition-colors"
              style={{
                background: "var(--color-bg-card)",
                borderColor: "var(--color-border)",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-hover)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "var(--color-bg-card)")}
            >
              <div className="text-sm font-medium">{s.title}</div>
              <div className="text-xs mt-0.5" style={{ color: "var(--color-text-muted)" }}>
                {s.subtitle}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function MessageList({ messages }: { messages: Message[] }) {
  return (
    <div className="max-w-3xl mx-auto px-3 sm:px-6 py-4 sm:py-6 flex flex-col gap-4 sm:gap-5">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 mt-0.5"
          style={{ background: "var(--color-accent-bg)", color: "var(--color-accent)" }}
        >
          U
        </div>
      )}
      <div className="flex flex-col gap-1 max-w-[80%]">
        {/* progress hint — 응답 작성 중에 본문이 비어 있을 때만 */}
        {!isUser && message.streaming && !message.content && message.progress && (
          <ProgressHint progress={message.progress} />
        )}
        <div
          className="px-4 py-2.5 rounded-2xl whitespace-pre-wrap text-[15px] leading-relaxed"
          style={
            isUser
              ? { background: "var(--color-accent)", color: "white" }
              : { background: "var(--color-bg-card)", color: "var(--color-text)" }
          }
        >
          {message.content || (message.streaming ? "…" : "")}
          {message.streaming && message.content && (
            <span className="inline-block w-1.5 h-4 ml-0.5 animate-pulse" style={{ background: "var(--color-text-muted)" }} />
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * "생각하는 중 (3s)" / "도구 실행: file_ops (5s)" 같은 진행 상태 줄.
 *
 * 1초마다 리렌더해 경과 시간을 갱신한다. busy 상태가 풀리면 부모가
 * 이 컴포넌트를 unmount 하므로 타이머 정리만 신경 쓰면 된다.
 */
function ProgressHint({ progress }: { progress: NonNullable<Message["progress"]> }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const elapsed = Math.max(0, Math.floor((now - progress.startedAt) / 1000));
  const label = progress.stage === "tool"
    ? `도구 실행: ${progress.toolName ?? "?"}`
    : "생각하는 중";
  const completedSuffix = progress.toolsCompleted
    ? ` · 도구 ${progress.toolsCompleted}회 완료`
    : "";
  return (
    <div
      className="text-xs px-3 py-1 rounded-full inline-flex items-center gap-2 self-start"
      style={{ background: "var(--color-bg-hover)", color: "var(--color-text-muted)" }}
    >
      <span className="inline-block w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "var(--color-accent)" }} />
      <span>{label} ({elapsed}s){completedSuffix}</span>
    </div>
  );
}
