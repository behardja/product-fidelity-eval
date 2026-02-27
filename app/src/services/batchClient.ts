export interface BatchStartResponse {
  batch_id: string;
  image_count: number;
}

export interface BatchEvent {
  sku?: string;
  status: "running" | "passed" | "failed" | "error" | "complete" | "cancelled" | "keepalive";
  score?: number;
  attempt?: number;
  message?: string;
  total?: number;
}

export async function startBatch(
  prefix: string,
  imageUris: string[],
  runAll: boolean
): Promise<BatchStartResponse> {
  const res = await fetch("/api/batch/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prefix,
      image_uris: imageUris,
      run_all: runAll,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || res.statusText);
  }
  return res.json();
}

export function subscribeBatchStatus(
  onEvent: (event: BatchEvent) => void,
  onDone: () => void
): AbortController {
  const ctrl = new AbortController();

  (async () => {
    try {
      const res = await fetch("/api/batch/status", {
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        onDone();
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event: BatchEvent = JSON.parse(line.slice(6));
              if (event.status === "keepalive") continue;
              onEvent(event);
              if (event.status === "complete") {
                onDone();
                return;
              }
            } catch {
              // skip unparseable
            }
          }
        }
      }
    } catch (err: any) {
      if (err.name !== "AbortError") {
        console.error("Batch SSE error:", err);
      }
    } finally {
      onDone();
    }
  })();

  return ctrl;
}

export async function cancelBatch(): Promise<void> {
  await fetch("/api/batch/cancel", { method: "POST" });
}

export function batchReportUrl(): string {
  return "/api/batch/report";
}
