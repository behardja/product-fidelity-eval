import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { sendMessage, type ChatMessage, type StreamChunk, type MessagePart } from "../services/adkClient";
import { thumbnailUrl } from "../services/gcsClient";

/**
 * Preprocess agent text before passing to ReactMarkdown:
 * 1. Strip inline base64 image markdown (huge data URIs that stream slowly)
 * 2. Convert bare gs:// image URIs into markdown images via the thumbnail proxy
 */
function preprocessText(text: string): string {
  // Strip ![alt](data:image/...;base64,...) — these are huge and redundant
  // since we render the same images via the GCS thumbnail proxy
  let result = text.replace(
    /!\[[^\]]*\]\(data:image\/[^)]+\)/g,
    ""
  );

  // Convert bare gs:// image URIs to markdown images via thumbnail proxy
  result = result.replace(
    /(?<!!]\()gs:\/\/[^\s)\]]+\.(?:png|jpg|jpeg|webp)/gi,
    (match) => {
      const filename = match.split("/").pop() ?? match;
      return `![${filename}](${thumbnailUrl(match)})`;
    }
  );

  // Make report filename clickable — opens in a new tab via /api/report
  result = result.replace(
    /product_candidate_report\.html/g,
    "[product_candidate_report.html](/api/report)"
  );

  return result;
}

/**
 * Normalize text for deduplication comparison.
 * Strips whitespace and base64 data URIs so two messages that differ only
 * in formatting or embedded image data are treated as duplicates.
 */
function normalizeForDedup(text: string): string {
  return text
    .replace(/!\[[^\]]*\]\(data:image\/[^)]+\)/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

interface ChatPanelProps {
  sessionId: string | null;
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  pendingMessage: string | null;
  clearPendingMessage: () => void;
}

const ChatPanel: React.FC<ChatPanelProps> = ({
  sessionId,
  messages,
  setMessages,
  pendingMessage,
  clearPendingMessage,
}) => {
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Track the index of the message currently being streamed into
  const streamingIdxRef = useRef<number | null>(null);
  const streamingAuthorRef = useRef<string | null>(null);

  // Lightbox state
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Handle pending message from Evaluate button
  useEffect(() => {
    if (pendingMessage && sessionId && !streaming) {
      doSend(pendingMessage, undefined);
      clearPendingMessage();
    }
  }, [pendingMessage, sessionId]);

  const handleChunk = (chunk: StreamChunk) => {
    setMessages((prev) => {
      if (chunk.partial) {
        // Streaming token — accumulate into current message
        if (
          streamingIdxRef.current !== null &&
          streamingIdxRef.current < prev.length &&
          streamingAuthorRef.current === chunk.author
        ) {
          const updated = [...prev];
          updated[streamingIdxRef.current] = {
            ...updated[streamingIdxRef.current],
            text: updated[streamingIdxRef.current].text + chunk.text,
          };
          return updated;
        } else {
          // New author — but check if this is a duplicate of an existing message
          // (sub-agent re-emitting the same content as the parent)
          streamingIdxRef.current = prev.length;
          streamingAuthorRef.current = chunk.author;
          return [
            ...prev,
            { role: "agent" as const, text: chunk.text, author: chunk.author },
          ];
        }
      } else {
        // Final (non-partial) event — contains complete text for this turn.
        // Deduplicate: if the last agent message already has the same text
        // (from a different author/sub-agent), skip this event.
        const normalized = normalizeForDedup(chunk.text);
        const lastAgent = [...prev].reverse().find((m) => m.role === "agent");
        if (lastAgent && normalizeForDedup(lastAgent.text) === normalized) {
          // Duplicate — skip it
          streamingIdxRef.current = null;
          streamingAuthorRef.current = null;
          return prev;
        }

        if (
          streamingIdxRef.current !== null &&
          streamingIdxRef.current < prev.length &&
          streamingAuthorRef.current === chunk.author
        ) {
          // Replace the accumulated streaming message with the final text
          const updated = [...prev];
          updated[streamingIdxRef.current] = {
            ...updated[streamingIdxRef.current],
            text: chunk.text,
          };
          streamingIdxRef.current = null;
          streamingAuthorRef.current = null;
          return updated;
        } else {
          // No prior streaming message for this author — add as new
          streamingIdxRef.current = null;
          streamingAuthorRef.current = null;
          return [
            ...prev,
            { role: "agent" as const, text: chunk.text, author: chunk.author },
          ];
        }
      }
    });
  };

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [pendingFile, setPendingFile] = useState<{ name: string; mime: string; data: string } | null>(null);

  const doSend = async (text: string, file?: { name: string; mime: string; data: string }) => {
    if (!sessionId || streaming) return;
    if (!text.trim() && !file) return;

    const displayText = file
      ? text.trim() ? `${text.trim()} [${file.name}]` : `[${file.name}]`
      : text.trim();
    const userMsg: ChatMessage = { role: "user", text: displayText };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setPendingFile(null);
    setStreaming(true);
    streamingIdxRef.current = null;
    streamingAuthorRef.current = null;

    const parts: MessagePart[] = [];
    if (file) {
      parts.push({ inline_data: { mime_type: file.mime, data: file.data } });
    }
    if (text.trim()) {
      parts.push({ text: text.trim() });
    } else if (file) {
      parts.push({ text: `Evaluate this uploaded image: ${file.name}` });
    }

    await sendMessage(sessionId, parts, handleChunk, () => {
      streamingIdxRef.current = null;
      streamingAuthorRef.current = null;
      setStreaming(false);
    });
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = (reader.result as string).split(",")[1];
      setPendingFile({ name: file.name, mime: file.type, data: base64 });
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doSend(input, pendingFile ?? undefined);
    }
  };

  return (
    <div className="flex flex-col flex-1 bg-white dark:bg-[#0d1117] relative">
      {/* Image lightbox */}
      {lightboxSrc && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={() => setLightboxSrc(null)}
        >
          <button
            onClick={() => setLightboxSrc(null)}
            className="absolute top-4 right-4 p-2 text-white/80 hover:text-white bg-black/40 rounded-full transition-colors"
          >
            <span className="material-symbols-outlined text-2xl">close</span>
          </button>
          <img
            src={lightboxSrc}
            alt="Full size preview"
            className="max-w-[90vw] max-h-[90vh] rounded-xl shadow-2xl object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}

      {/* Chat header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-border-dark bg-white dark:bg-[#0d1117]">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-surface-dark flex items-center justify-center border border-slate-200 dark:border-border-dark">
              <span className="material-symbols-outlined text-primary text-xl">
                smart_toy
              </span>
            </div>
            <div className="absolute bottom-0 right-0 w-3 h-3 bg-green-500 rounded-full border-2 border-white dark:border-[#0d1117]" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white">
              Fidelity Agent
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {sessionId ? "Online" : "Connecting..."}
            </p>
          </div>
        </div>
        <button className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
          <span className="material-symbols-outlined">more_vert</span>
        </button>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-700 bg-slate-50 dark:bg-[#0d1117]"
      >
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-slate-400 text-sm">
            Send a message or select an image to evaluate.
          </div>
        )}
        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="flex flex-col items-end max-w-[80%] gap-1">
                <div className="bg-primary text-white px-5 py-3 rounded-2xl rounded-tr-sm shadow-sm">
                  <p className="text-sm leading-relaxed">{msg.text}</p>
                </div>
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="flex gap-3 max-w-[85%]">
                <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-surface-dark flex-shrink-0 flex items-center justify-center mt-1">
                  <span className="material-symbols-outlined text-primary text-sm">
                    smart_toy
                  </span>
                </div>
                <div className="flex flex-col gap-1">
                  <div className="bg-white dark:bg-surface-dark border border-slate-200 dark:border-border-dark px-5 py-3 rounded-2xl rounded-tl-sm shadow-sm prose prose-sm dark:prose-invert max-w-none">
                    <ReactMarkdown
                      urlTransform={(url) => url}
                      components={{
                        img: ({ src, alt }) => (
                          <img
                            src={src}
                            alt={alt ?? ""}
                            className="max-w-full rounded-lg my-2 cursor-pointer hover:opacity-80 transition-opacity"
                            onClick={() => src && setLightboxSrc(src)}
                          />
                        ),
                        a: ({ href, children }) => (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary underline hover:text-blue-400"
                          >
                            {children}
                          </a>
                        ),
                      }}
                    >
                      {preprocessText(msg.text)}
                    </ReactMarkdown>
                  </div>
                </div>
              </div>
            </div>
          )
        )}
        {streaming && (
          <div className="flex justify-start">
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-surface-dark flex-shrink-0 flex items-center justify-center mt-1">
                <span className="material-symbols-outlined text-primary text-sm">
                  smart_toy
                </span>
              </div>
              <div className="bg-white dark:bg-surface-dark border border-slate-200 dark:border-border-dark px-5 py-3 rounded-2xl rounded-tl-sm shadow-sm">
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-24 bg-slate-200 dark:bg-border-dark rounded-full overflow-hidden">
                    <div className="h-full bg-primary w-2/3 animate-pulse" />
                  </div>
                  <span className="text-xs text-slate-400">Thinking...</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-4 bg-white dark:bg-[#111318] border-t border-slate-200 dark:border-border-dark shrink-0">
        {pendingFile && (
          <div className="flex items-center gap-2 mb-2 px-2">
            <span className="material-symbols-outlined text-primary text-[18px]">image</span>
            <span className="text-xs text-slate-300 truncate">{pendingFile.name}</span>
            <button
              onClick={() => setPendingFile(null)}
              className="text-slate-400 hover:text-red-400 transition-colors"
            >
              <span className="material-symbols-outlined text-[16px]">close</span>
            </button>
          </div>
        )}
        <div className="relative flex items-end gap-2 bg-slate-50 dark:bg-surface-dark border border-slate-200 dark:border-border-dark rounded-xl p-2 shadow-sm focus-within:ring-1 focus-within:ring-primary focus-within:border-primary transition-all">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={handleFileSelect}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-200 dark:hover:bg-border-dark transition-colors"
          >
            <span className="material-symbols-outlined">add_circle</span>
          </button>
          <textarea
            className="w-full bg-transparent border-none focus:ring-0 text-sm text-slate-900 dark:text-white placeholder-slate-500 resize-none py-2.5 max-h-32"
            placeholder="Ask agent to evaluate..."
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button
            onClick={() => doSend(input, pendingFile ?? undefined)}
            disabled={streaming || (!input.trim() && !pendingFile)}
            className="p-2 bg-primary text-white rounded-lg hover:bg-blue-600 transition-colors shadow-sm mb-0.5 disabled:opacity-40"
          >
            <span className="material-symbols-outlined text-[20px]">send</span>
          </button>
        </div>
        <p className="text-[10px] text-center text-slate-400 mt-2">
          AI can make mistakes. Please verify important information.
        </p>
      </div>
    </div>
  );
};

export default ChatPanel;
