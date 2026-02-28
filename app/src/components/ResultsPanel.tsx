import React, { useState, useRef, useEffect, useMemo, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import {
  sendMessage,
  type ChatMessage,
  type StreamChunk,
  type MessagePart,
} from "../services/adkClient";
import { thumbnailUrl } from "../services/gcsClient";
import type { UploadedImage } from "./ImageBrowser";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface PendingEval {
  uri: string;
  userPrompt: string;
  uploadedImages: UploadedImage[];
}

interface ResultsPanelProps {
  sessionId: string | null;
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  pendingEval: PendingEval | null;
  clearPendingEval: () => void;
  referenceUri: string | null;
}

interface Attempt {
  imageUri: string | null;
  score: number | null;
  passing: string[];
  failing: string[];
}

type PipelineStep =
  | "description"
  | "generation"
  | "evaluation"
  | "refinement"
  | "report";

interface PipelineState {
  currentStep: PipelineStep;
  attempts: Attempt[];
  reportReady: boolean;
}

/** A completed or in-progress evaluation run */
interface EvalRun {
  id: number;
  referenceUri: string;
  userPrompt: string;
  uploadedImages: UploadedImage[];
  messages: ChatMessage[];
  status: "running" | "complete" | "error";
  errorMessage?: string;
}

const STEPS: { key: PipelineStep; label: string; icon: string }[] = [
  { key: "description", label: "Description", icon: "description" },
  { key: "generation", label: "Generation", icon: "image" },
  { key: "evaluation", label: "Evaluation", icon: "analytics" },
  { key: "refinement", label: "Refinement", icon: "auto_fix_high" },
  { key: "report", label: "Report", icon: "summarize" },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function preprocessMarkdown(text: string): string {
  let result = text.replace(/!\[[^\]]*\]\(data:image\/[^)]+\)/g, "");
  result = result.replace(
    /(?<!!]\()gs:\/\/[^\s)\]]+\.(?:png|jpg|jpeg|webp)/gi,
    (match) => {
      const filename = match.split("/").pop() ?? match;
      return `![${filename}](${thumbnailUrl(match)})`;
    }
  );
  result = result.replace(
    /product_candidate_report\.html/g,
    "[product_candidate_report.html](/api/report)"
  );
  return result;
}

function normalizeForDedup(text: string): string {
  return text
    .replace(/!\[[^\]]*\]\(data:image\/[^)]+\)/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function extractImageUris(text: string): string[] {
  const matches = text.match(/gs:\/\/[^\s)\]]+\.(?:png|jpg|jpeg|webp)/gi);
  return matches ? [...new Set(matches)] : [];
}

function extractScores(text: string): number[] {
  const scores: number[] = [];
  const patterns = [
    /(?:score|rating|fidelity)[:\s]+(\d+(?:\.\d+)?)\s*(?:\/\s*10)?/gi,
    /(\d+(?:\.\d+)?)\s*(?:\/\s*10)?\s*(?:score|rating)/gi,
  ];
  for (const pat of patterns) {
    let m;
    while ((m = pat.exec(text)) !== null) {
      let val = parseFloat(m[1]);
      if (val > 1 && val <= 10) val = val / 10;
      if (val >= 0 && val <= 1) scores.push(val);
    }
  }
  return scores;
}

function inferStep(text: string): PipelineStep {
  const lower = text.toLowerCase();
  if (lower.includes("report") || lower.includes("product_candidate_report"))
    return "report";
  if (
    lower.includes("refin") ||
    lower.includes("re-generat") ||
    lower.includes("attempt 2") ||
    lower.includes("second attempt") ||
    lower.includes("regenerat")
  )
    return "refinement";
  if (
    lower.includes("evaluat") ||
    lower.includes("score") ||
    lower.includes("fidelity") ||
    lower.includes("criteria")
  )
    return "evaluation";
  if (lower.includes("generat") || lower.includes("imagen"))
    return "generation";
  return "description";
}

function parsePipeline(messages: ChatMessage[]): PipelineState {
  const text = messages
    .filter((m) => m.role === "agent")
    .map((m) => m.text)
    .join("\n");

  const imageUris = extractImageUris(text);
  const scores = extractScores(text);
  const reportReady = /product_candidate_report\.html/i.test(text);
  const currentStep = inferStep(text);

  const attempts: Attempt[] = [];
  const numAttempts = Math.max(imageUris.length, scores.length, 0);
  for (let i = 0; i < numAttempts; i++) {
    const passing: string[] = [];
    const failing: string[] = [];
    const score = scores[i] ?? null;
    if (score !== null) {
      if (score >= 0.7) passing.push("Meets fidelity threshold");
      else failing.push("Below fidelity threshold");
    }
    attempts.push({ imageUri: imageUris[i] ?? null, score, passing, failing });
  }

  return { currentStep, attempts, reportReady };
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

/** Pipeline step indicator — only marks steps done up to the reached step */
const StepIndicator: React.FC<{
  pipeline: PipelineState;
  isRunning: boolean;
}> = ({ pipeline, isRunning }) => {
  const stepIndex = STEPS.findIndex((s) => s.key === pipeline.currentStep);
  return (
    <div className="bg-white dark:bg-surface-dark rounded-xl border border-slate-200 dark:border-border-dark p-4 shadow-sm">
      <div className="flex items-center justify-between">
        {STEPS.map((step, i) => {
          const isActive = i === stepIndex && isRunning;
          const isDone = i < stepIndex || (i === stepIndex && !isRunning);
          return (
            <React.Fragment key={step.key}>
              {i > 0 && (
                <div
                  className={`flex-1 h-0.5 mx-1 rounded ${isDone ? "bg-primary" : "bg-slate-200 dark:bg-border-dark"}`}
                />
              )}
              <div className="flex flex-col items-center gap-1">
                <div
                  className={`w-9 h-9 rounded-full flex items-center justify-center text-sm transition-colors ${
                    isDone
                      ? "bg-primary text-white"
                      : isActive
                        ? "bg-primary/20 text-primary border-2 border-primary"
                        : "bg-slate-100 dark:bg-border-dark text-slate-400"
                  }`}
                >
                  {isDone ? (
                    <span className="material-symbols-outlined text-[18px]">check</span>
                  ) : isActive ? (
                    <span className="material-symbols-outlined text-[18px] animate-pulse">{step.icon}</span>
                  ) : (
                    <span className="material-symbols-outlined text-[18px]">{step.icon}</span>
                  )}
                </div>
                <span className={`text-[10px] font-medium ${isDone || isActive ? "text-primary" : "text-slate-400"}`}>
                  {step.label}
                </span>
              </div>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

/** Render a single evaluation run — supports collapsed mode */
const RunCard: React.FC<{
  run: EvalRun;
  runIndex: number;
  totalRuns: number;
  defaultCollapsed?: boolean;
  onLightbox: (src: string) => void;
  onRetry?: () => void;
}> = ({ run, runIndex, totalRuns, defaultCollapsed = false, onLightbox, onRetry }) => {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [showRaw, setShowRaw] = useState(true);

  const pipeline = useMemo(() => parsePipeline(run.messages), [run.messages]);
  const hasAgentOutput = run.messages.some((m) => m.role === "agent");
  const isRunning = run.status === "running";
  const hasGcsRef = !!run.referenceUri;
  const filename = hasGcsRef
    ? (run.referenceUri.split("/").pop() ?? run.referenceUri)
    : run.uploadedImages.length > 0
      ? run.uploadedImages[0].name
      : "Uploaded images";
  const headerThumb = hasGcsRef
    ? thumbnailUrl(run.referenceUri)
    : run.uploadedImages.length > 0
      ? run.uploadedImages[0].preview
      : null;

  // Auto-expand when this run starts streaming
  useEffect(() => {
    if (isRunning) setCollapsed(false);
  }, [isRunning]);

  return (
    <div className="space-y-4">
      {/* Run header — clickable to collapse/expand */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-3 px-4 py-3 rounded-xl bg-white dark:bg-surface-dark border border-slate-200 dark:border-border-dark shadow-sm hover:bg-slate-50 dark:hover:bg-border-dark transition-colors text-left"
      >
        <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${isRunning ? "bg-amber-500 animate-pulse" : run.status === "error" ? "bg-red-500" : "bg-green-500"}`} />
        {headerThumb ? (
          <img
            src={headerThumb}
            alt=""
            className="w-8 h-8 rounded object-cover border border-slate-200 dark:border-border-dark flex-shrink-0"
          />
        ) : (
          <div className="w-8 h-8 rounded bg-slate-100 dark:bg-border-dark flex items-center justify-center flex-shrink-0">
            <span className="material-symbols-outlined text-slate-400 text-[16px]">image</span>
          </div>
        )}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-bold text-slate-900 dark:text-white">
            {totalRuns > 1 ? `#${runIndex + 1} — ` : ""}{filename}
          </span>
          {run.userPrompt && (
            <span className="text-xs text-slate-400 ml-2 truncate" title={run.userPrompt}>
              "{run.userPrompt}"
            </span>
          )}
        </div>
        <span className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full flex-shrink-0 ${
          isRunning
            ? "bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400"
            : run.status === "error"
              ? "bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400"
              : "bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400"
        }`}>
          {isRunning ? "Running" : run.status === "error" ? "Error" : "Done"}
        </span>
        <span className="material-symbols-outlined text-slate-400 text-[18px] flex-shrink-0">
          {collapsed ? "expand_more" : "expand_less"}
        </span>
      </button>

      {/* Collapsible body */}
      {!collapsed && (
        <>
          {/* Pipeline progress (per run) */}
          {hasAgentOutput && <StepIndicator pipeline={pipeline} isRunning={isRunning} />}

          {/* Reference images */}
          <div className="bg-white dark:bg-surface-dark rounded-xl border border-slate-200 dark:border-border-dark p-4 shadow-sm">
            <h4 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-3">
              Reference
            </h4>
            <div className="flex items-start gap-3 flex-wrap">
              {hasGcsRef && (
                <div className="relative">
                  <img
                    src={thumbnailUrl(run.referenceUri)}
                    alt="Reference"
                    className="w-20 h-20 rounded-lg object-cover border border-slate-200 dark:border-border-dark cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => onLightbox(thumbnailUrl(run.referenceUri))}
                  />
                  <span className="absolute -top-1 -left-1 bg-primary text-white text-[8px] font-bold px-1.5 py-0.5 rounded-full">
                    GCS
                  </span>
                </div>
              )}
              {run.uploadedImages.map((img, i) => (
                <div key={i} className="relative">
                  <img
                    src={img.preview}
                    alt={img.name}
                    className="w-20 h-20 rounded-lg object-cover border border-slate-200 dark:border-border-dark cursor-pointer hover:opacity-80 transition-opacity"
                    onClick={() => onLightbox(img.preview)}
                  />
                  <span className="absolute -top-1 -left-1 bg-slate-600 text-white text-[8px] font-bold px-1.5 py-0.5 rounded-full">
                    Upload
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Attempt cards */}
          {pipeline.attempts.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                Generation Attempts
              </h4>
              {pipeline.attempts.map((attempt, i) => (
                <div
                  key={i}
                  className="bg-white dark:bg-surface-dark rounded-xl border border-slate-200 dark:border-border-dark p-4 shadow-sm"
                >
                  <div className="flex items-start gap-4">
                    {attempt.imageUri && (
                      <img
                        src={thumbnailUrl(attempt.imageUri)}
                        alt={`Attempt ${i + 1}`}
                        className="w-24 h-24 rounded-lg object-cover border border-slate-200 dark:border-border-dark cursor-pointer hover:opacity-80 transition-opacity flex-shrink-0"
                        onClick={() => onLightbox(thumbnailUrl(attempt.imageUri!))}
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          Attempt {i + 1}
                        </span>
                        {attempt.score !== null && (
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold ${
                              attempt.score >= 0.7
                                ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400"
                                : "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"
                            }`}
                          >
                            <span className="material-symbols-outlined text-[14px]">
                              {attempt.score >= 0.7 ? "check_circle" : "cancel"}
                            </span>
                            {(attempt.score * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                      <div className="space-y-1">
                        {attempt.passing.map((p, j) => (
                          <div key={`p-${j}`} className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
                            <span className="material-symbols-outlined text-[14px]">check</span>
                            {p}
                          </div>
                        ))}
                        {attempt.failing.map((f, j) => (
                          <div key={`f-${j}`} className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
                            <span className="material-symbols-outlined text-[14px]">close</span>
                            {f}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Streaming indicator */}
          {isRunning && (
            <div className="flex items-center gap-3 px-4 py-3 bg-white dark:bg-surface-dark rounded-xl border border-slate-200 dark:border-border-dark shadow-sm">
              <div className="h-1.5 w-24 bg-slate-200 dark:bg-border-dark rounded-full overflow-hidden">
                <div className="h-full bg-primary w-2/3 animate-pulse" />
              </div>
              <span className="text-xs text-slate-400">Processing...</span>
            </div>
          )}

          {/* Error banner with retry */}
          {run.status === "error" && (
            <div className="flex items-start gap-3 px-4 py-3 bg-red-50 dark:bg-red-900/10 rounded-xl border border-red-200 dark:border-red-800/30">
              <span className="material-symbols-outlined text-red-500 text-xl flex-shrink-0 mt-0.5">error</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-red-700 dark:text-red-400">
                  Pipeline Error
                </p>
                <p className="text-xs text-red-600 dark:text-red-400/80 mt-1">
                  {run.errorMessage || "The evaluation was interrupted. This is usually caused by Vertex AI rate limits (429). Wait 30-60 seconds and retry."}
                </p>
              </div>
              {onRetry && (
                <button
                  onClick={onRetry}
                  className="flex-shrink-0 h-8 px-3 flex items-center gap-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-colors"
                >
                  <span className="material-symbols-outlined text-[16px]">refresh</span>
                  Retry
                </button>
              )}
            </div>
          )}

          {/* Raw agent output — open by default */}
          {hasAgentOutput && (
            <div className="border border-slate-200 dark:border-border-dark rounded-xl overflow-hidden">
              <button
                onClick={() => setShowRaw(!showRaw)}
                className="w-full flex items-center justify-between px-4 py-3 bg-white dark:bg-surface-dark text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-border-dark transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px]">terminal</span>
                  Raw Agent Output
                </div>
                <span className="material-symbols-outlined text-[18px]">
                  {showRaw ? "expand_less" : "expand_more"}
                </span>
              </button>
              {showRaw && (
                <div className="px-5 py-4 bg-slate-50 dark:bg-[#0d1117] border-t border-slate-200 dark:border-border-dark prose prose-sm dark:prose-invert max-w-none overflow-x-auto">
                  {run.messages
                    .filter((m) => m.role === "agent")
                    .map((msg, i) => (
                      <div key={i} className="mb-4 last:mb-0">
                        <ReactMarkdown
                          urlTransform={(url) => url}
                          components={{
                            img: ({ src, alt }) => (
                              <img
                                src={src}
                                alt={alt ?? ""}
                                className="max-w-full rounded-lg my-2 cursor-pointer hover:opacity-80 transition-opacity"
                                onClick={() => src && onLightbox(src)}
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
                          {preprocessMarkdown(msg.text)}
                        </ReactMarkdown>
                      </div>
                    ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

const ResultsPanel: React.FC<ResultsPanelProps> = ({
  sessionId,
  messages,
  setMessages,
  pendingEval,
  clearPendingEval,
  referenceUri,
}) => {
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const streamingIdxRef = useRef<number | null>(null);
  const streamingAuthorRef = useRef<string | null>(null);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Multi-run tracking
  const [completedRuns, setCompletedRuns] = useState<EvalRun[]>([]);
  const [currentRunContext, setCurrentRunContext] = useState<{
    uri: string;
    userPrompt: string;
    uploadedImages: UploadedImage[];
  } | null>(null);
  const runIdCounter = useRef(0);

  // Scroll to top when a new run starts (newest on top)
  const scrollToTop = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, []);

  // Handle pending eval — snapshot previous run, start new one
  useEffect(() => {
    if (pendingEval && sessionId && !streaming) {
      // Snapshot current messages into completed run (if any agent output exists)
      if (currentRunContext && messages.some((m) => m.role === "agent")) {
        setCompletedRuns((prev) => [
          ...prev,
          {
            id: runIdCounter.current++,
            referenceUri: currentRunContext.uri,
            userPrompt: currentRunContext.userPrompt,
            uploadedImages: currentRunContext.uploadedImages,
            messages: [...messages],
            status: "complete",
          },
        ]);
        setMessages([]);
      }

      // Set new context and send
      setCurrentRunContext({
        uri: pendingEval.uri,
        userPrompt: pendingEval.userPrompt,
        uploadedImages: pendingEval.uploadedImages,
      });
      doSend(pendingEval);
      clearPendingEval();
      // Scroll to top after React processes the state updates
      setTimeout(scrollToTop, 50);
    }
  }, [pendingEval, sessionId]);

  const handleStreamError = useCallback((err: string) => {
    setErrorMessage(err);
  }, []);

  const handleStreamDone = useCallback(() => {
    streamingIdxRef.current = null;
    streamingAuthorRef.current = null;
    setStreaming(false);
  }, []);

  const handleChunk = useCallback((chunk: StreamChunk) => {
    setMessages((prev) => {
      if (chunk.partial) {
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
          streamingIdxRef.current = prev.length;
          streamingAuthorRef.current = chunk.author;
          return [
            ...prev,
            { role: "agent" as const, text: chunk.text, author: chunk.author },
          ];
        }
      } else {
        const normalized = normalizeForDedup(chunk.text);
        const lastAgent = [...prev].reverse().find((m) => m.role === "agent");
        if (lastAgent && normalizeForDedup(lastAgent.text) === normalized) {
          streamingIdxRef.current = null;
          streamingAuthorRef.current = null;
          return prev;
        }
        if (
          streamingIdxRef.current !== null &&
          streamingIdxRef.current < prev.length &&
          streamingAuthorRef.current === chunk.author
        ) {
          const updated = [...prev];
          updated[streamingIdxRef.current] = {
            ...updated[streamingIdxRef.current],
            text: chunk.text,
          };
          streamingIdxRef.current = null;
          streamingAuthorRef.current = null;
          return updated;
        } else {
          streamingIdxRef.current = null;
          streamingAuthorRef.current = null;
          return [
            ...prev,
            { role: "agent" as const, text: chunk.text, author: chunk.author },
          ];
        }
      }
    });
  }, [setMessages]);

  const doSend = async (eval_: PendingEval) => {
    if (!sessionId || streaming) return;

    const displayParts: string[] = [];
    if (eval_.uri) displayParts.push(eval_.uri);
    if (eval_.userPrompt) displayParts.push(`Prompt: ${eval_.userPrompt}`);
    if (eval_.uploadedImages.length > 0)
      displayParts.push(
        `${eval_.uploadedImages.length} uploaded image${eval_.uploadedImages.length > 1 ? "s" : ""}`
      );
    setMessages((prev) => [
      ...prev,
      { role: "user" as const, text: displayParts.join(" | ") },
    ]);
    setStreaming(true);
    setErrorMessage(null);
    streamingIdxRef.current = null;
    streamingAuthorRef.current = null;

    const parts: MessagePart[] = [];
    for (const img of eval_.uploadedImages) {
      parts.push({ inline_data: { mime_type: img.mime, data: img.data } });
    }
    let textContent = eval_.uri
      ? `Evaluate ${eval_.uri}`
      : "Evaluate the uploaded product images";
    if (eval_.userPrompt) {
      textContent += `\n\nUser prompt: ${eval_.userPrompt}`;
    }
    parts.push({ text: textContent });

    await sendMessage(sessionId, parts, handleChunk, handleStreamDone, handleStreamError);
  };

  // Build the current (active) run from live messages
  const currentRun: EvalRun | null = useMemo(() => {
    if (!currentRunContext) return null;
    const status: EvalRun["status"] = streaming
      ? "running"
      : errorMessage
        ? "error"
        : "complete";
    return {
      id: runIdCounter.current,
      referenceUri: currentRunContext.uri,
      userPrompt: currentRunContext.userPrompt,
      uploadedImages: currentRunContext.uploadedImages,
      messages,
      status,
      errorMessage: errorMessage ?? undefined,
    };
  }, [currentRunContext, messages, streaming, errorMessage]);

  // All runs to display — newest first
  const allRuns = useMemo(() => {
    const runs: EvalRun[] = [];
    // Current (active/most recent) run first
    if (currentRun) runs.push(currentRun);
    // Then completed runs in reverse chronological order
    for (let i = completedRuns.length - 1; i >= 0; i--) {
      runs.push(completedRuns[i]);
    }
    return runs;
  }, [completedRuns, currentRun]);

  // Retry handler: re-submit the current run's evaluation
  const handleRetry = useCallback(() => {
    if (!currentRunContext || streaming) return;
    setErrorMessage(null);
    setMessages([]);
    doSend({
      uri: currentRunContext.uri,
      userPrompt: currentRunContext.userPrompt,
      uploadedImages: currentRunContext.uploadedImages,
    });
    setTimeout(scrollToTop, 50);
  }, [currentRunContext, streaming, scrollToTop]);

  // Detect abrupt termination: stream ended without reaching the report step.
  const prevStreamingRef = useRef(false);
  useEffect(() => {
    const justStopped = prevStreamingRef.current && !streaming;
    prevStreamingRef.current = streaming;
    if (errorMessage) return;

    if (justStopped && messages.some((m) => m.role === "agent")) {
      const agentText = messages
        .filter((m) => m.role === "agent")
        .map((m) => m.text)
        .join("\n")
        .toLowerCase();
      const hasReport = agentText.includes("product_candidate_report");
      if (!hasReport) {
        setErrorMessage("The pipeline was interrupted before completing. This is usually caused by Vertex AI rate limits (429). Wait 30-60 seconds before retrying.");
      }
    }
  }, [messages, streaming, errorMessage]);

  // Check if any run has a report
  const anyReportReady = useMemo(
    () =>
      allRuns.some((r) =>
        r.messages.some(
          (m) =>
            m.role === "agent" &&
            /product_candidate_report\.html/i.test(m.text)
        )
      ),
    [allRuns]
  );

  const hasAnyResults = allRuns.length > 0;

  // Reset everything when session changes (New Chat)
  useEffect(() => {
    if (!sessionId) {
      setCompletedRuns([]);
      setCurrentRunContext(null);
      setErrorMessage(null);
      runIdCounter.current = 0;
    }
  }, [sessionId]);

  return (
    <div className="flex flex-col flex-1 bg-white dark:bg-[#0d1117] relative">
      {/* Lightbox */}
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

      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-border-dark bg-white dark:bg-[#0d1117]">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-surface-dark flex items-center justify-center border border-slate-200 dark:border-border-dark">
              <span className="material-symbols-outlined text-primary text-xl">
                analytics
              </span>
            </div>
            {streaming && (
              <div className="absolute bottom-0 right-0 w-3 h-3 bg-amber-500 rounded-full border-2 border-white dark:border-[#0d1117] animate-pulse" />
            )}
            {!streaming && hasAnyResults && errorMessage && (
              <div className="absolute bottom-0 right-0 w-3 h-3 bg-red-500 rounded-full border-2 border-white dark:border-[#0d1117]" />
            )}
            {!streaming && hasAnyResults && !errorMessage && (
              <div className="absolute bottom-0 right-0 w-3 h-3 bg-green-500 rounded-full border-2 border-white dark:border-[#0d1117]" />
            )}
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white">
              Evaluation Results
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {streaming
                ? "Running evaluation..."
                : hasAnyResults
                  ? `${allRuns.length} evaluation${allRuns.length > 1 ? "s" : ""} complete`
                  : sessionId
                    ? "Ready"
                    : "Connecting..."}
            </p>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-700 bg-slate-50 dark:bg-[#0d1117]"
      >
        {/* Empty state */}
        {!hasAnyResults && !streaming && (
          <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-3">
            <span className="material-symbols-outlined text-5xl">science</span>
            <p className="text-sm">Select an image and click Evaluate to begin</p>
          </div>
        )}

        {/* Report link — at top when available */}
        {anyReportReady && (
          <div className="bg-white dark:bg-surface-dark rounded-xl border border-primary/30 p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <span className="material-symbols-outlined text-primary text-xl">
                    summarize
                  </span>
                </div>
                <div>
                  <p className="text-sm font-bold text-slate-900 dark:text-white">
                    Evaluation Report
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Includes all evaluations in this session
                  </p>
                </div>
              </div>
              <a
                href={`/api/report?t=${Date.now()}`}
                target="_blank"
                rel="noopener noreferrer"
                className="h-9 px-4 flex items-center gap-2 rounded-lg bg-primary text-white text-sm font-bold hover:bg-blue-600 transition-colors shadow-sm"
              >
                <span className="material-symbols-outlined text-[18px]">
                  open_in_new
                </span>
                View Report
              </a>
            </div>
          </div>
        )}

        {/* All runs — newest first, older ones collapsed */}
        {allRuns.map((run, i) => (
          <RunCard
            key={run.id}
            run={run}
            runIndex={allRuns.length - 1 - i}
            totalRuns={allRuns.length}
            defaultCollapsed={i > 0}
            onLightbox={setLightboxSrc}
            onRetry={i === 0 && run.status === "error" ? handleRetry : undefined}
          />
        ))}
      </div>
    </div>
  );
};

export default ResultsPanel;
