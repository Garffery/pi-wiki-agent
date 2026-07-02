import { useChatStore } from "../../stores/chatStore";

export function Footer() {
  const contextUsage = useChatStore((s) => s.contextUsage);
  const isStreaming = useChatStore((s) => s.isStreaming);

  return (
    <div className="h-8 bg-[var(--bg-main)] border-t border-[var(--border-default)] flex items-center gap-3 flex-shrink-0" style={{ paddingLeft: 0, paddingRight: 64 }}>
      {contextUsage && (
        <span className="text-sm text-[var(--text-tertiary)] tabular-nums">
          {Math.round(contextUsage.tokens / 1000)}k / {Math.round(contextUsage.contextWindow / 1000)}k tokens
        </span>
      )}
      <div className="flex-1" />
      {isStreaming && (
        <div className="flex items-center gap-1.5 text-sm font-medium text-[var(--accent-text)]">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--accent)] opacity-75" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[var(--accent)]" />
          </span>
          生成中...
        </div>
      )}
    </div>
  );
}
