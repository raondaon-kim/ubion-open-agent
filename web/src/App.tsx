import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatScreen } from "./components/ChatScreen";
import {
  type ConversationMeta,
  deleteConversation as apiDeleteConversation,
  listConversations,
} from "./api/client";
import { DebugDrawer, appendDebug, type DebugEvent } from "./components/DebugDrawer";

function App() {
  const [activePanel, setActivePanel] = useState<"chat" | "skills" | "memory" | "settings">("chat");
  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugEvents, setDebugEvents] = useState<DebugEvent[]>([]);

  const refreshConversations = useCallback(async () => {
    try {
      const list = await listConversations();
      setConversations(list);
    } catch {
      // 서버 미기동/오류 시 조용히 빈 목록 유지
    }
  }, []);

  useEffect(() => {
    refreshConversations();
  }, [refreshConversations]);

  // Ctrl+Shift+D 로 디버그 드로어 토글
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey && e.shiftKey && (e.key === "D" || e.key === "d")) {
        e.preventDefault();
        setDebugOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function handleNewChat() {
    setCurrentId(null);
    setActivePanel("chat");
  }

  function handleSelectConversation(id: string) {
    setCurrentId(id);
    setActivePanel("chat");
  }

  async function handleDeleteConversation(id: string) {
    await apiDeleteConversation(id);
    if (currentId === id) setCurrentId(null);
    await refreshConversations();
  }

  const pushDebug = useCallback((ev: Omit<DebugEvent, "ts"> & { ts?: number }) => {
    appendDebug(setDebugEvents, ev);
  }, []);

  return (
    <div className="flex h-screen w-screen bg-[var(--color-bg)] text-[var(--color-text)]">
      <Sidebar
        activePanel={activePanel}
        onSelectPanel={setActivePanel}
        conversations={conversations}
        currentId={currentId}
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
      />
      <main className="flex-1 flex flex-col overflow-hidden">
        <ChatScreen
          panel={activePanel}
          currentId={currentId}
          onConversationSaved={(meta) => {
            setCurrentId(meta.id);
            refreshConversations();
          }}
          onDebugEvent={pushDebug}
          onToggleDebug={() => setDebugOpen((v) => !v)}
        />
      </main>
      <DebugDrawer
        open={debugOpen}
        onClose={() => setDebugOpen(false)}
        events={debugEvents}
        onClear={() => setDebugEvents([])}
      />
    </div>
  );
}

export default App;
