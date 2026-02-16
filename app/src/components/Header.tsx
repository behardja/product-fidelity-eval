import React from "react";

interface HeaderProps {
  onNewChat: () => void;
}

const Header: React.FC<HeaderProps> = ({ onNewChat }) => {
  return (
    <header className="flex items-center justify-between whitespace-nowrap border-b border-solid border-slate-200 dark:border-border-dark px-6 py-3 bg-white dark:bg-[#111318] flex-shrink-0 z-20">
      <div className="flex items-center gap-4">
        <div className="size-8 flex items-center justify-center text-primary">
          <span className="material-symbols-outlined text-3xl">token</span>
        </div>
        <h2 className="text-slate-900 dark:text-white text-lg font-bold leading-tight tracking-[-0.015em]">
          Product Fidelity Evaluator
        </h2>
      </div>
      <div className="flex items-center gap-2">
        <div className="relative mr-2">
          <button className="flex items-center justify-between min-w-[140px] h-9 px-3 rounded-lg bg-slate-100 dark:bg-border-dark text-slate-900 dark:text-white text-sm font-bold tracking-[0.015em] border border-transparent hover:border-slate-300 dark:hover:border-slate-600 transition-all focus:outline-none focus:ring-2 focus:ring-primary/50">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-[20px] text-primary">
                smart_toy
              </span>
              <span>Agent Mode</span>
            </div>
            <span className="material-symbols-outlined text-[18px] text-slate-500">
              expand_more
            </span>
          </button>
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
