import { useState } from "react";
import type { ToolCallEntry } from "../../types/events";

interface Props {
  toolCall: ToolCallEntry;
}

export function ToolCallCard({ toolCall }: Props) {
  const [expanded, setExpanded] = useState(false);
  const isRunning = toolCall.status === "running";
  const isError = toolCall.isError && !isRunning;

  const borderColor = isRunning
    ? "border-[var(--warning)]/30"
    : isError
    ? "border-[var(--error)]/30"
    : "border-[var(--border-default)]";

  const bgColor = isRunning
    ? "bg-[var(--warning-soft)]"
    : isError
    ? "bg-[var(--error-soft)]"
    : "bg-[var(--bg-input)]/50";

  const dotColor = isRunning
    ? "bg-[var(--warning)]"
    : isError
    ? "bg-[var(--error)]"
    : "bg-[var(--success)]";

  return (
    <div className={`rounded-xl border ${borderColor} ${bgColor} text-sm overflow-hidden transition-all`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-3 py-2 flex items-center gap-2.5 hover:bg-black/[0.02] transition-colors"
      >
        <span className="relative flex h-1.5 w-1.5 flex-shrink-0">
          {isRunning && (
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${dotColor} opacity-75`} />
          )}
          <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${dotColor}`} />
        </span>

        <span className="font-medium text-[var(--text-primary)] text-sm">{toolCall.name}</span>

        {isRunning && (
          <span className="text-sm text-[var(--text-tertiary)]">运行中...</span>
        )}

        {!isRunning && toolCall.result !== undefined && (
          <span className="text-sm text-[var(--text-tertiary)] truncate flex-1">
            {formatResult(toolCall.result)}
          </span>
        )}

        <svg
          className={`w-4 h-4 text-[var(--text-tertiary)] ml-auto transition-transform duration-[var(--transition-fast)] flex-shrink-0 ${
            expanded ? "rotate-180" : ""
          }`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-[var(--border-subtle)] px-3 py-2.5 space-y-2.5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1">
              参数
            </div>
            <pre className="text-[var(--text-secondary)] whitespace-pre-wrap font-mono text-sm leading-relaxed">
              {formatJson(toolCall.args)}
            </pre>
          </div>
          {toolCall.result !== undefined && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)] mb-1">
                结果
              </div>
              <pre
                className={`whitespace-pre-wrap font-mono text-sm leading-relaxed ${
                  isError ? "text-[var(--error)]" : "text-[var(--text-secondary)]"
                }`}
              >
                {formatJson(toolCall.result)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function formatResult(result: unknown): string {
  if (typeof result === "string") {
    return result.length > 120 ? result.slice(0, 120) + "..." : result;
  }
  const s = JSON.stringify(result, null, 0);
  return s.length > 120 ? s.slice(0, 120) + "..." : s;
}

function formatJson(val: unknown): string {
  if (typeof val === "string") return val;
  try {
    return JSON.stringify(val, null, 2);
  } catch {
    return String(val);
  }
}
