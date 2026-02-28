import { fetchEventSource } from "@microsoft/fetch-event-source";

const APP_NAME = "product_fidelity_agent";
const USER_ID = "user1";

export interface Session {
  id: string;
}

export async function createSession(): Promise<Session> {
  const res = await fetch(
    `/apps/${APP_NAME}/users/${USER_ID}/sessions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: {} }),
    }
  );
  if (!res.ok) throw new Error(`Create session failed: ${res.statusText}`);
  return res.json();
}

export interface ChatMessage {
  role: "user" | "agent";
  text: string;
  author?: string;
}

export interface StreamChunk {
  text: string;
  author: string;
  partial: boolean;
}

export interface MessagePart {
  text?: string;
  inline_data?: { mime_type: string; data: string };
}

export async function sendMessage(
  sessionId: string,
  parts: MessagePart[],
  onChunk: (chunk: StreamChunk) => void,
  onDone: () => void,
  onError?: (error: string) => void
): Promise<void> {
  const ctrl = new AbortController();

  try {
    await fetchEventSource("/run_sse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_name: APP_NAME,
        user_id: USER_ID,
        session_id: sessionId,
        new_message: { role: "user", parts },
        streaming: true,
      }),
      signal: ctrl.signal,
      onmessage(ev) {
        try {
          const data = JSON.parse(ev.data);

          // Detect server-side errors in the SSE stream
          if (data.error) {
            const errMsg = typeof data.error === "string" ? data.error : JSON.stringify(data.error);
            onError?.(errMsg);
            return;
          }

          const isPartial = data.partial === true;
          if (data.content?.parts) {
            const texts: string[] = [];
            for (const part of data.content.parts) {
              if (part.text) texts.push(part.text);
            }
            const combined = texts.join("");
            if (combined) {
              onChunk({
                text: combined,
                author: data.author ?? "agent",
                partial: isPartial,
              });
            }
          }
        } catch {
          // skip unparseable events
        }
      },
      onerror(err) {
        console.error("SSE error:", err);
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("429") || msg.toLowerCase().includes("rate")) {
          onError?.("Rate limited (429). The Vertex AI API quota has been exceeded. Please wait 30-60 seconds and retry.");
        } else {
          onError?.(`Stream error: ${msg}`);
        }
        throw err;
      },
      onclose() {
        // Prevent auto-reconnection which causes duplicate output
        ctrl.abort();
      },
      openWhenHidden: true,
    });
  } catch (err: any) {
    // Ignore AbortError from our own ctrl.abort()
    if (err instanceof DOMException && err.name === "AbortError") return;
    if (err.name !== "AbortError") {
      console.error("Fetch event source error:", err);
    }
  } finally {
    onDone();
  }
}
