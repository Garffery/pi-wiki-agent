import { useState } from "react";

interface Props {
  thinking: string;
  isStreaming?: boolean;
}

export function ThinkingBlock({ thinking, isStreaming }: Props) {
  const [expanded, setExpanded] = useState(!isStreaming);

  return (
    <div className="mb-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-sm text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors group w-full"
      >
        <svg
          className={`w-4 h-4 transition-transform duration-[var(--transition-fast)] ${expanded ? "rotate-90" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <span className="font-medium text-[var(--accent-text)]">
          {isStreaming ? "思考中..." : "思考过程"}
        </span>
        {!isStreaming && (
          <span className="text-[var(--text-tertiary)]/60 tabular-nums">
            ({thinking.length.toLocaleString()} 字符)
          </span>
        )}
      </button>
      {expanded && (
        <div className="mt-2 pl-5 border-l-2 border-[var(--accent)]/20 text-sm text-[var(--text-secondary)] whitespace-pre-wrap max-h-64 overflow-y-auto leading-relaxed">
          {thinking}
          {isStreaming && (
            <span className="inline-block w-[7px] h-4 bg-[var(--accent)]/60 ml-0.5 animate-pulse align-middle rounded-sm" />
          )}
        </div>
      )}
    </div>
  );
}
