import { useState, useEffect, useCallback } from "react";
import Header from "./components/Header";
import ImageBrowser from "./components/ImageBrowser";
import ChatPanel from "./components/ChatPanel";
import { createSession, type ChatMessage } from "./services/adkClient";

function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selectedUri, setSelectedUri] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);

  const initSession = useCallback(async () => {
    try {
      const session = await createSession();
      setSessionId(session.id);
      setMessages([]);
    } catch (e) {
      console.error("Failed to create session:", e);
    }
  }, []);

  useEffect(() => {
    initSession();
  }, [initSession]);

  const handleEvaluate = () => {
    if (!selectedUri) return;
    setPendingMessage(`Evaluate ${selectedUri}`);
  };

  const handleNewChat = () => {
    setMessages([]);
    setSessionId(null);
    initSession();
  };

  return (
    <>
      <Header onNewChat={handleNewChat} />
      <main className="flex flex-1 overflow-hidden relative">
        <ImageBrowser
          selectedUri={selectedUri}
          onSelectImage={setSelectedUri}
          onEvaluate={handleEvaluate}
        />
        <ChatPanel
          sessionId={sessionId}
          messages={messages}
          setMessages={setMessages}
          pendingMessage={pendingMessage}
          clearPendingMessage={() => setPendingMessage(null)}
        />
      </main>
    </>
  );
}

export default App;
