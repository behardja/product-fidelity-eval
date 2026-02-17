import React, { useState } from "react";
import ImageCard from "./ImageCard";
import { listImages, type GcsListResponse } from "../services/gcsClient";
import type { AppMode } from "./Header";

interface ImageBrowserProps {
  selectedUri: string | null;
  onSelectImage: (uri: string) => void;
  onEvaluate: () => void;
  mode?: AppMode;
  checkedUris?: Set<string>;
  onToggleCheck?: (uri: string) => void;
  onSelectAll?: () => void;
  onDeselectAll?: () => void;
  onRunBatch?: () => void;
  currentPrefix?: string;
  onPrefixChange?: (prefix: string) => void;
}

const ImageBrowser: React.FC<ImageBrowserProps> = ({
  selectedUri,
  onSelectImage,
  onEvaluate,
  mode = "agent",
  checkedUris,
  onToggleCheck,
  onSelectAll,
  onDeselectAll,
  onRunBatch,
  currentPrefix,
  onPrefixChange,
}) => {
  const [prefix, setPrefix] = useState(currentPrefix ?? "");
  const [data, setData] = useState<GcsListResponse | null>(null);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isBatch = mode === "batch";

  const browse = async (p = page) => {
    let cleanPrefix = prefix.trim();
    if (cleanPrefix.startsWith("gs://")) {
      cleanPrefix = cleanPrefix.slice(5);
    }
    if (!cleanPrefix) return;

    setLoading(true);
    setError(null);
    try {
      const result = await listImages(cleanPrefix, p);
      setData(result);
      setPage(p);
      onPrefixChange?.(prefix.trim());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to list images");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") browse(0);
  };

  const goPrev = () => {
    if (page > 0) browse(page - 1);
  };
  const goNext = () => {
    if (data && page < data.total_pages - 1) browse(page + 1);
  };

  const displayPrefix = prefix.startsWith("gs://") ? prefix : `gs://${prefix}`;

  const allChecked =
    data && data.images.length > 0 && checkedUris
      ? data.images.every((uri) => checkedUris.has(uri))
      : false;

  const handleSelectAllToggle = () => {
    if (allChecked) {
      onDeselectAll?.();
    } else {
      onSelectAll?.();
    }
  };

  return (
    <div className="flex flex-col w-full lg:w-7/12 xl:w-2/3 border-r border-slate-200 dark:border-border-dark bg-slate-50 dark:bg-[#111318] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-border-dark bg-white dark:bg-[#111318]">
        <div className="flex flex-col">
          <h1 className="text-xl font-bold text-slate-900 dark:text-white">
            GCS Image Browser
          </h1>
          {prefix && (
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 mt-1">
              <span className="material-symbols-outlined text-base">
                folder_open
              </span>
              <span className="font-mono">{displayPrefix}</span>
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <div className="relative">
            <span className="absolute left-2.5 top-2 text-slate-400 material-symbols-outlined text-[18px]">
              search
            </span>
            <input
              className="h-9 pl-9 pr-4 rounded-lg bg-slate-100 dark:bg-border-dark border-none text-sm text-slate-900 dark:text-white focus:ring-1 focus:ring-primary placeholder-slate-500 w-48"
              placeholder="gs://bucket/prefix/"
              type="text"
              value={prefix}
              onChange={(e) => setPrefix(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
          <button
            onClick={() => browse(0)}
            className="h-9 px-3 flex items-center justify-center rounded-lg bg-primary text-white text-sm font-bold hover:bg-blue-600 transition-colors"
          >
            Browse
          </button>
        </div>
      </div>

      {/* Batch toolbar */}
      {isBatch && data && data.images.length > 0 && (
        <div className="flex items-center justify-between px-6 py-2 border-b border-slate-200 dark:border-border-dark bg-white dark:bg-[#111318]">
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={allChecked}
                onChange={handleSelectAllToggle}
                className="w-4 h-4 rounded border-slate-300 text-primary focus:ring-primary"
              />
              Select All
            </label>
            {checkedUris && checkedUris.size > 0 && (
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {checkedUris.size} image{checkedUris.size !== 1 ? "s" : ""}{" "}
                selected
              </span>
            )}
          </div>
          <button
            onClick={onRunBatch}
            disabled={!checkedUris || checkedUris.size === 0}
            className="flex items-center gap-2 h-8 px-3 rounded-lg bg-primary text-white text-xs font-bold hover:bg-blue-600 transition-colors shadow-sm disabled:opacity-40"
          >
            <span className="material-symbols-outlined text-[16px]">
              play_arrow
            </span>
            Run Batch
          </button>
        </div>
      )}

      {/* Grid */}
      <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-700">
        {loading && (
          <div className="flex items-center justify-center h-40 text-slate-400">
            Loading...
          </div>
        )}
        {error && (
          <div className="flex items-center justify-center h-40 text-red-400">
            {error}
          </div>
        )}
        {!loading && !error && data && data.images.length === 0 && (
          <div className="flex items-center justify-center h-40 text-slate-400">
            No images found
          </div>
        )}
        {!loading && !error && data && data.images.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
            {data.images.map((uri) => (
              <ImageCard
                key={uri}
                uri={uri}
                selected={uri === selectedUri}
                onSelect={() => onSelectImage(uri)}
                mode={mode}
                checked={checkedUris?.has(uri) ?? false}
                onToggleCheck={() => onToggleCheck?.(uri)}
              />
            ))}
          </div>
        )}
        {!data && !loading && !error && (
          <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-2">
            <span className="material-symbols-outlined text-5xl">
              cloud_upload
            </span>
            <p className="text-sm">Enter a GCS prefix and click Browse</p>
          </div>
        )}
      </div>

      {/* Selected image info + Evaluate (agent mode only) */}
      {!isBatch && selectedUri && (
        <div className="px-6 py-3 border-t border-slate-200 dark:border-border-dark bg-white dark:bg-[#111318] flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Selected
            </p>
            <p className="text-sm font-mono text-slate-900 dark:text-white truncate">
              {selectedUri}
            </p>
          </div>
          <button
            onClick={onEvaluate}
            className="flex-shrink-0 h-9 px-4 flex items-center gap-2 rounded-lg bg-primary text-white text-sm font-bold hover:bg-blue-600 transition-colors shadow-sm"
          >
            <span className="material-symbols-outlined text-[18px]">
              play_arrow
            </span>
            Evaluate
          </button>
        </div>
      )}

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="border-t border-slate-200 dark:border-border-dark p-4 bg-white dark:bg-[#111318] flex items-center justify-between shrink-0">
          <button
            onClick={goPrev}
            disabled={page === 0}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-border-dark transition-colors disabled:opacity-40"
          >
            <span className="material-symbols-outlined text-lg">
              arrow_back
            </span>
            Previous
          </button>
          <span className="text-sm text-slate-500 dark:text-slate-400 font-medium">
            Page {page + 1} of {data.total_pages}
          </span>
          <button
            onClick={goNext}
            disabled={page >= data.total_pages - 1}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-white bg-primary hover:bg-blue-600 transition-colors shadow-sm disabled:opacity-40"
          >
            Next
            <span className="material-symbols-outlined text-lg">
              arrow_forward
            </span>
          </button>
        </div>
      )}
    </div>
  );
};

export default ImageBrowser;
