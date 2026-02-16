import { useState, useEffect, useCallback } from "react";
import Header, { type AppMode } from "./components/Header";
import ImageBrowser from "./components/ImageBrowser";
import ChatPanel from "./components/ChatPanel";
import BatchDashboard from "./components/BatchDashboard";
import { createSession, type ChatMessage } from "./services/adkClient";
import { listImages } from "./services/gcsClient";

function App() {
  const [mode, setMode] = useState<AppMode>("agent");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selectedUri, setSelectedUri] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);

  // Batch mode state
  const [checkedUris, setCheckedUris] = useState<Set<string>>(new Set());
  const [batchPrefix, setBatchPrefix] = useState("");
  const [allImageUris, setAllImageUris] = useState<string[]>([]);

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

  // Batch multi-select handlers
  const handleToggleCheck = (uri: string) => {
    setCheckedUris((prev) => {
      const next = new Set(prev);
      if (next.has(uri)) {
        next.delete(uri);
      } else {
        next.add(uri);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    setCheckedUris((prev) => {
      const next = new Set(prev);
      for (const uri of allImageUris) {
        next.add(uri);
      }
      return next;
    });
  };

  const handleDeselectAll = () => {
    setCheckedUris(new Set());
  };

  const handlePrefixChange = async (prefix: string) => {
    setBatchPrefix(prefix);
    // Fetch all images for this prefix (for select all)
    try {
      let cleanPrefix = prefix.trim();
      if (cleanPrefix.startsWith("gs://")) {
        cleanPrefix = cleanPrefix.slice(5);
      }
      const result = await listImages(cleanPrefix, 0, 100);
      setAllImageUris(result.images);
    } catch {
      setAllImageUris([]);
    }
  };

  const handleRunBatch = () => {
    // The BatchDashboard handles the actual batch start
    // This just signals to show the dashboard with the selected images
  };

  return (
    <>
      <Header mode={mode} onModeChange={setMode} onNewChat={handleNewChat} />
      <main className="flex flex-1 overflow-hidden relative">
        <ImageBrowser
          selectedUri={selectedUri}
          onSelectImage={setSelectedUri}
          onEvaluate={handleEvaluate}
          mode={mode}
          checkedUris={checkedUris}
          onToggleCheck={handleToggleCheck}
          onSelectAll={handleSelectAll}
          onDeselectAll={handleDeselectAll}
          onRunBatch={handleRunBatch}
          currentPrefix={batchPrefix}
          onPrefixChange={handlePrefixChange}
        />
        {mode === "agent" ? (
          <ChatPanel
            sessionId={sessionId}
            messages={messages}
            setMessages={setMessages}
            pendingMessage={pendingMessage}
            clearPendingMessage={() => setPendingMessage(null)}
          />
        ) : (
          <BatchDashboard
            selectedUris={Array.from(checkedUris)}
            prefix={batchPrefix}
            runAll={false}
          />
        )}
      </main>
    </>
  );
}

export default App;
