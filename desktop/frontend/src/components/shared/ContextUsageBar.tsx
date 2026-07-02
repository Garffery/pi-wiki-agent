import { useChatStore } from "../../stores/chatStore";

export function ContextUsageBar() {
  const usage = useChatStore((s) => s.contextUsage);
  if (!usage) return null;

  return (
    <div className="flex items-center gap-2 text-xs text-[#a0a0b0]">
      <span>
        {usage.percent.toFixed(0)}% ({Math.round(usage.tokens / 1000)}k/{Math.round(usage.contextWindow / 1000)}k)
      </span>
      <div className="w-24 h-1 bg-[#1a1a2e] rounded-full overflow-hidden">
        <div
          className="h-full bg-[#e94560] transition-all"
          style={{ width: `${Math.min(usage.percent, 100)}%` }}
        />
      </div>
    </div>
  );
}
