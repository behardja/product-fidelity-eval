import React, { useState, useRef, useEffect } from "react";

export type AppMode = "agent" | "batch";

interface HeaderProps {
  mode: AppMode;
  onModeChange: (mode: AppMode) => void;
  onNewChat: () => void;
}

const Header: React.FC<HeaderProps> = ({ mode, onModeChange, onNewChat }) => {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const modeLabel = mode === "agent" ? "Agent Mode" : "Batch Mode";
  const modeIcon = mode === "agent" ? "smart_toy" : "batch_prediction";

  return (
    <header className="flex items-center justify-between whitespace-nowrap border-b border-solid border-slate-200 dark:border-border-dark px-6 py-3 bg-white dark:bg-[#111318] flex-shrink-0 z-20">
      <div className="flex items-center gap-4">
        <div className="size-8 flex items-center justify-center text-primary">
          <span className="material-symbols-outlined text-3xl">token</span>
        </div>
        <h2 className="text-slate-900 dark:text-white text-lg font-bold leading-tight tracking-[-0.015em]">
          Product Generation & Fidelity Evaluator
        </h2>
      </div>
      <div className="flex items-center gap-2">
        <div className="relative mr-2" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center justify-between min-w-[140px] h-9 px-3 rounded-lg bg-slate-100 dark:bg-border-dark text-slate-900 dark:text-white text-sm font-bold tracking-[0.015em] border border-transparent hover:border-slate-300 dark:hover:border-slate-600 transition-all focus:outline-none focus:ring-2 focus:ring-primary/50"
          >
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-[20px] text-primary">
                {modeIcon}
              </span>
              <span>{modeLabel}</span>
            </div>
            <span className="material-symbols-outlined text-[18px] text-slate-500">
              expand_more
            </span>
          </button>
          {dropdownOpen && (
            <div className="absolute right-0 mt-1 w-48 bg-white dark:bg-[#1c1f26] rounded-lg shadow-lg border border-slate-200 dark:border-border-dark z-50 overflow-hidden">
              <button
                onClick={() => {
                  onModeChange("agent");
                  setDropdownOpen(false);
                }}
                className={`w-full flex items-center gap-2 px-4 py-2.5 text-sm text-left hover:bg-slate-50 dark:hover:bg-border-dark transition-colors ${
                  mode === "agent"
                    ? "text-primary font-bold"
                    : "text-slate-700 dark:text-slate-300"
                }`}
              >
                <span className="material-symbols-outlined text-[18px]">
                  smart_toy
                </span>
                Agent Mode
                {mode === "agent" && (
                  <span className="material-symbols-outlined text-[16px] ml-auto">
                    check
                  </span>
                )}
              </button>
              <button
                onClick={() => {
                  onModeChange("batch");
                  setDropdownOpen(false);
                }}
                className={`w-full flex items-center gap-2 px-4 py-2.5 text-sm text-left hover:bg-slate-50 dark:hover:bg-border-dark transition-colors ${
                  mode === "batch"
                    ? "text-primary font-bold"
                    : "text-slate-700 dark:text-slate-300"
                }`}
              >
                <span className="material-symbols-outlined text-[18px]">
                  batch_prediction
                </span>
                Batch Mode
                {mode === "batch" && (
                  <span className="material-symbols-outlined text-[16px] ml-auto">
                    check
                  </span>
                )}
              </button>
            </div>
          )}
        </div>
        <button className="flex cursor-pointer items-center justify-center overflow-hidden rounded-lg h-9 bg-slate-100 dark:bg-border-dark text-slate-900 dark:text-white gap-2 text-sm font-bold leading-normal tracking-[0.015em] px-3 transition-colors hover:bg-slate-200 dark:hover:bg-[#3b4354]">
          <span className="material-symbols-outlined text-[20px]">
            cloud_download
          </span>
          <span className="hidden sm:inline">Export Report</span>
        </button>
        <button
          onClick={onNewChat}
          className="flex cursor-pointer items-center justify-center overflow-hidden rounded-lg h-9 bg-slate-100 dark:bg-border-dark text-slate-900 dark:text-white gap-2 text-sm font-bold leading-normal tracking-[0.015em] px-3 transition-colors hover:bg-slate-200 dark:hover:bg-[#3b4354]"
        >
          <span className="material-symbols-outlined text-[20px]">
            settings
          </span>
        </button>
        <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-primary to-blue-400 ml-2" />
      </div>
    </header>
  );
};

export default Header;
