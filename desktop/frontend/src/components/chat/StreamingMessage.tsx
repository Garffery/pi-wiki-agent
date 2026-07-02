import { ThinkingBlock } from "../tools/ThinkingBlock";
import { ToolCallCard } from "../tools/ToolCallCard";
import { MarkdownRenderer } from "../shared/MarkdownRenderer";

interface Props {
  streaming: {
    content: string;
    thinking: string;
    pendingToolCalls: Map<string, any>;
  };
}

export function StreamingMessage({ streaming }: Props) {
  const toolCalls = Array.from(streaming.pendingToolCalls.values());
  const hasContent = streaming.content.length > 0;
  const hasThinking = streaming.thinking.length > 0;
  const hasTools = toolCalls.length > 0;

  return (
    <div className="flex justify-start gap-3 mb-6 animate-fade-in">
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 via-indigo-500 to-blue-500 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-[var(--shadow-xs)] shadow-violet-400/30 relative">
        <span className="text-white text-base font-bold">π</span>
        <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-[var(--accent)] border-2 border-[var(--bg-main)] animate-pulse" />
      </div>

      <div className="max-w-[78%] min-w-0">
        {hasThinking && <ThinkingBlock thinking={streaming.thinking} isStreaming />}
        {hasContent && (
          <div className="text-base leading-relaxed break-words">
            <MarkdownRenderer content={streaming.content} />
          </div>
        )}
        {hasTools && (
          <div className="mt-3 space-y-2">
            {toolCalls.map((tc) => (
              <ToolCallCard key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}
        {!hasContent && !hasTools && (
          <div className="flex items-center gap-3 py-1">
            <div className="flex gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]/50 animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]/50 animate-bounce" style={{ animationDelay: "120ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]/50 animate-bounce" style={{ animationDelay: "240ms" }} />
            </div>
            <span className="text-base text-[var(--text-tertiary)]">思考中...</span>
          </div>
        )}
      </div>
    </div>
  );
}
