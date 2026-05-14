import { useEffect, useState } from "react";
import type { Panel } from "../types";
import type { ConversationMeta } from "../api/client";

interface Props {
  activePanel: Panel;
  onSelectPanel: (panel: Panel) => void;
  conversations: ConversationMeta[];
  currentId: string | null;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
}

interface NavItem {
  id: Panel;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: "skills", label: "스킬", icon: "★" },
  { id: "memory", label: "메모리", icon: "✦" },
  { id: "settings", label: "설정", icon: "⚙" },
];

const MOBILE_BREAKPOINT = 768;

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.innerWidth < MOBILE_BREAKPOINT,
  );
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return isMobile;
}

export function Sidebar(props: Props) {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);

  function handleSelect(p: Panel) {
    props.onSelectPanel(p);
    if (isMobile) setOpen(false);
  }

  function handleNewChat() {
    props.onNewChat();
    if (isMobile) setOpen(false);
  }

  function handleSelectConv(id: string) {
    props.onSelectConversation(id);
    if (isMobile) setOpen(false);
  }

  if (isMobile) {
    return (
      <>
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="메뉴 열기"
          className="fixed top-3 left-3 z-30 w-9 h-9 rounded-md flex items-center justify-center"
          style={{
            background: "var(--color-bg-card)",
            border: "1px solid var(--color-border)",
            color: "var(--color-text)",
          }}
        >
          ☰
        </button>

        {open && (
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            style={{ background: "rgba(0, 0, 0, 0.4)" }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              className="w-[260px] h-full flex flex-col border-r"
              style={{
                background: "var(--color-bg-sidebar)",
                borderColor: "var(--color-border)",
              }}
            >
              <SidebarBody
                {...props}
                onSelect={handleSelect}
                onNewChat={handleNewChat}
                onSelectConv={handleSelectConv}
                onClose={() => setOpen(false)}
                showClose
              />
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <aside
      className="w-[260px] shrink-0 h-full flex flex-col border-r"
      style={{
        background: "var(--color-bg-sidebar)",
        borderColor: "var(--color-border)",
      }}
    >
      <SidebarBody
        {...props}
        onSelect={handleSelect}
        onNewChat={handleNewChat}
        onSelectConv={handleSelectConv}
      />
    </aside>
  );
}

interface BodyProps {
  activePanel: Panel;
  conversations: ConversationMeta[];
  currentId: string | null;
  onSelect: (p: Panel) => void;
  onNewChat: () => void;
  onSelectConv: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onClose?: () => void;
  showClose?: boolean;
}

function SidebarBody({
  activePanel,
  conversations,
  currentId,
  onSelect,
  onNewChat,
  onSelectConv,
  onDeleteConversation,
  onClose,
  showClose = false,
}: BodyProps) {
  return (
    <>
      <div
        className="flex items-center gap-2 px-4 h-14 border-b"
        style={{ borderColor: "var(--color-border)" }}
      >
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-sm font-semibold"
          style={{
            background: "var(--color-accent-bg)",
            color: "var(--color-accent)",
          }}
        >
          U
        </div>
        <span className="font-medium tracking-tight">Ubion 에이전트</span>
        {showClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="ml-auto w-8 h-8 rounded-md text-sm"
            style={{ color: "var(--color-text-muted)" }}
          >
            ✕
          </button>
        )}
      </div>

      <div className="px-3 py-3">
        <button
          type="button"
          onClick={onNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-colors"
          style={{
            background: "var(--color-bg-card)",
            color: "var(--color-text)",
            borderColor: "var(--color-border)",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "var(--color-bg-card)")}
        >
          <span>＋</span>
          <span>새 대화</span>
        </button>
      </div>

      <nav className="px-2 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => {
          const active = item.id === activePanel;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-left transition-colors"
              style={{
                background: active ? "var(--color-bg-hover)" : "transparent",
                color: active ? "var(--color-text)" : "var(--color-text-muted)",
              }}
              onMouseEnter={(e) => {
                if (!active) e.currentTarget.style.background = "var(--color-bg-hover)";
              }}
              onMouseLeave={(e) => {
                if (!active) e.currentTarget.style.background = "transparent";
              }}
            >
              <span className="w-4 text-center">{item.icon}</span>
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="px-3 mt-4 flex-1 overflow-y-auto">
        <div
          className="text-xs uppercase tracking-wider px-1 mb-1"
          style={{ color: "var(--color-text-dim)" }}
        >
          최근 대화
        </div>
        {conversations.length === 0 ? (
          <div
            className="text-sm px-1 py-2"
            style={{ color: "var(--color-text-dim)" }}
          >
            아직 대화가 없습니다.
          </div>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {conversations.map((c) => {
              const active =
                activePanel === "chat" && c.id === currentId;
              return (
                <li
                  key={c.id}
                  className="group flex items-center gap-1"
                >
                  <button
                    type="button"
                    onClick={() => onSelectConv(c.id)}
                    className="flex-1 text-left px-3 py-2 rounded-lg text-sm truncate"
                    style={{
                      background: active ? "var(--color-bg-hover)" : "transparent",
                      color: active ? "var(--color-text)" : "var(--color-text-muted)",
                    }}
                    onMouseEnter={(e) => {
                      if (!active) e.currentTarget.style.background = "var(--color-bg-hover)";
                    }}
                    onMouseLeave={(e) => {
                      if (!active) e.currentTarget.style.background = "transparent";
                    }}
                    title={c.title}
                  >
                    {c.title || "(제목 없음)"}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (window.confirm(`"${c.title}" 대화를 삭제할까요?`)) {
                        onDeleteConversation(c.id);
                      }
                    }}
                    aria-label="대화 삭제"
                    className="w-7 h-7 rounded-md text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ color: "var(--color-text-muted)" }}
                  >
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div
        className="mt-auto px-3 py-3 border-t"
        style={{ borderColor: "var(--color-border)" }}
      >
        <div className="flex items-center gap-3 px-1">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold"
            style={{
              background: "var(--color-accent-bg)",
              color: "var(--color-accent)",
            }}
          >
            ax
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-medium">ax 센터</span>
            <span
              className="text-xs"
              style={{ color: "var(--color-text-dim)" }}
            >
              Phase 1
            </span>
          </div>
        </div>
      </div>
    </>
  );
}
