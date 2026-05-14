import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatScreen } from "./components/ChatScreen";
import {
  type ConversationMeta,
  deleteConversation as apiDeleteConversation,
  listConversations,
} from "./api/client";

function App() {
  const [activePanel, setActivePanel] = useState<"chat" | "skills" | "memory" | "settings">("chat");
  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);

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
        />
      </main>
    </div>
  );
}

export default App;
