import React, { useState, useEffect, useRef } from "react";
import {
  startBatch,
  subscribeBatchStatus,
  cancelBatch,
  batchReportUrl,
  type BatchEvent,
} from "../services/batchClient";

interface ProgressRow {
  sku: string;
  status: "pending" | "running" | "passed" | "failed" | "error" | "cancelled";
  score?: number;
  attempt?: number;
  message?: string;
}

interface BatchDashboardProps {
  selectedUris: string[];
  prefix: string;
  runAll: boolean;
  onBatchComplete?: () => void;
}

const BatchDashboard: React.FC<BatchDashboardProps> = ({
  selectedUris,
  prefix,
  runAll,
  onBatchComplete,
}) => {
  const [rows, setRows] = useState<Map<string, ProgressRow>>(new Map());
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchDone, setBatchDone] = useState(false);
  const [imageCount, setImageCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const completedCount = Array.from(rows.values()).filter(
    (r) => r.status === "passed" || r.status === "failed" || r.status === "error"
  ).length;

  const passedCount = Array.from(rows.values()).filter(
    (r) => r.status === "passed"
  ).length;

  const failedCount = Array.from(rows.values()).filter(
    (r) => r.status === "failed"
  ).length;

  const handleStart = async () => {
    setError(null);
    setBatchDone(false);
    setRows(new Map());

    try {
      const resp = await startBatch(prefix, selectedUris, runAll);
      setImageCount(resp.image_count);
      setBatchRunning(true);

      // Initialize pending rows
      if (!runAll) {
        const initial = new Map<string, ProgressRow>();
        for (const uri of selectedUris) {
          const sku = uri.split("/").pop()?.replace(/\.[^.]+$/, "") ?? uri;
          initial.set(sku, { sku, status: "pending" });
        }
        setRows(initial);
      }

      const ctrl = subscribeBatchStatus(
        (event: BatchEvent) => {
          if (event.sku) {
            setRows((prev) => {
              const next = new Map(prev);
              next.set(event.sku!, {
                sku: event.sku!,
                status: event.status as ProgressRow["status"],
                score: event.score,
                attempt: event.attempt,
                message: event.message,
              });
              return next;
            });
          }
          if (event.status === "complete") {
            setBatchRunning(false);
            setBatchDone(true);
            onBatchComplete?.();
          }
        },
        () => {
          setBatchRunning(false);
        }
      );
      abortRef.current = ctrl;
    } catch (e: any) {
      setError(e.message || "Failed to start batch");
      setBatchRunning(false);
    }
  };

  const handleCancel = async () => {
    abortRef.current?.abort();
    await cancelBatch();
    setBatchRunning(false);
    setBatchDone(false);
  };

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const statusBadge = (status: ProgressRow["status"]) => {
    switch (status) {
      case "passed":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
            Passed
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
            Failed
          </span>
        );
      case "running":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 mr-1.5 animate-pulse" />
            Running
          </span>
        );
      case "error":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
            Error
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
            Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            Pending
          </span>
        );
    }
  };

  const sortedRows = Array.from(rows.values()).sort((a, b) => {
    const order = { running: 0, pending: 1, error: 2, failed: 3, passed: 4, cancelled: 5 };
    return (order[a.status] ?? 9) - (order[b.status] ?? 9);
  });

  return (
    <div className="flex flex-col flex-1 bg-white dark:bg-[#0d1117]">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-border-dark bg-white dark:bg-[#0d1117]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-surface-dark flex items-center justify-center border border-slate-200 dark:border-border-dark">
            <span className="material-symbols-outlined text-primary text-xl">
              batch_prediction
            </span>
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white">
              Batch Processing
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {batchRunning
                ? `Processing ${completedCount} / ${imageCount || rows.size}`
                : batchDone
                ? "Complete"
                : `${selectedUris.length} images selected`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!batchRunning && !batchDone && (
            <button
              onClick={handleStart}
              disabled={selectedUris.length === 0 && !runAll}
              className="flex items-center gap-2 h-9 px-4 rounded-lg bg-primary text-white text-sm font-bold hover:bg-blue-600 transition-colors shadow-sm disabled:opacity-40"
            >
              <span className="material-symbols-outlined text-[18px]">
                play_arrow
              </span>
              Run Batch
            </button>
          )}
          {batchRunning && (
            <button
              onClick={handleCancel}
              className="flex items-center gap-2 h-9 px-4 rounded-lg bg-red-500 text-white text-sm font-bold hover:bg-red-600 transition-colors shadow-sm"
            >
              <span className="material-symbols-outlined text-[18px]">
                stop
              </span>
              Cancel
            </button>
          )}
          {batchDone && (
            <a
              href={batchReportUrl()}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 h-9 px-4 rounded-lg bg-green-600 text-white text-sm font-bold hover:bg-green-700 transition-colors shadow-sm"
            >
              <span className="material-symbols-outlined text-[18px]">
                description
              </span>
              View Report
            </a>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {(batchRunning || batchDone) && imageCount > 0 && (
        <div className="px-6 py-3 border-b border-slate-200 dark:border-border-dark">
          <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
            <span>
              {completedCount} / {imageCount} complete
            </span>
            <span>
              {passedCount} passed, {failedCount} failed
            </span>
          </div>
          <div className="h-2 bg-slate-200 dark:bg-border-dark rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-300"
              style={{
                width: `${imageCount ? (completedCount / imageCount) * 100 : 0}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mx-6 mt-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg border border-red-200 dark:border-red-800">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-700">
        {sortedRows.length === 0 && !batchRunning && !batchDone && (
          <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-2">
            <span className="material-symbols-outlined text-5xl">
              batch_prediction
            </span>
            <p className="text-sm">
              Select images and click Run Batch to start processing.
            </p>
          </div>
        )}
        {sortedRows.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-border-dark">
                <th className="pb-3 font-medium">SKU</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Score</th>
                <th className="pb-3 font-medium">Attempts</th>
                <th className="pb-3 font-medium">Details</th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row) => (
                <tr
                  key={row.sku}
                  className="border-b border-slate-100 dark:border-border-dark"
                >
                  <td className="py-3 font-mono text-slate-900 dark:text-white">
                    {row.sku}
                  </td>
                  <td className="py-3">{statusBadge(row.status)}</td>
                  <td className="py-3 text-slate-700 dark:text-slate-300">
                    {row.score != null ? row.score.toFixed(2) : "--"}
                  </td>
                  <td className="py-3 text-slate-700 dark:text-slate-300">
                    {row.attempt ?? "--"}
                  </td>
                  <td className="py-3 text-slate-500 dark:text-slate-400 text-xs max-w-[200px] truncate">
                    {row.message ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default BatchDashboard;
