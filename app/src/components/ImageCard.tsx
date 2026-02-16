import React from "react";
import { thumbnailUrl } from "../services/gcsClient";

interface ImageCardProps {
  uri: string;
  selected: boolean;
  onSelect: () => void;
}

function skuFromUri(uri: string): string {
  const filename = uri.split("/").pop() ?? "";
  return filename.replace(/\.[^.]+$/, "");
}

const ImageCard: React.FC<ImageCardProps> = ({ uri, selected, onSelect }) => {
  const sku = skuFromUri(uri);

  return (
    <div
      onClick={onSelect}
      className={`group relative flex flex-col gap-2 p-2 rounded-xl cursor-pointer transition-all ${
        selected
          ? "bg-primary/10 border-2 border-primary"
          : "border border-transparent hover:bg-slate-200 dark:hover:bg-surface-dark"
      }`}
    >
      {selected && (
        <div className="absolute top-3 right-3 z-10">
          <div className="w-6 h-6 rounded-full bg-primary text-white flex items-center justify-center shadow-md">
            <span className="material-symbols-outlined text-sm font-bold">
              check
            </span>
          </div>
        </div>
      )}
      <div className="aspect-[4/5] w-full rounded-lg bg-slate-200 dark:bg-surface-dark overflow-hidden relative">
        <img
          src={thumbnailUrl(uri)}
          alt={sku}
          loading="lazy"
          className={`w-full h-full object-cover transition-opacity ${
            selected ? "" : "opacity-80 group-hover:opacity-100"
          }`}
        />
      </div>
      <div className="px-1">
        <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">
          {sku}
        </p>
        {selected && <p className="text-xs text-primary font-medium">Selected</p>}
      </div>
    </div>
  );
};

export default ImageCard;
