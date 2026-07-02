import type { ChatMessage } from "../../types/events";
import { ThinkingBlock } from "../tools/ThinkingBlock";
import { ToolCallCard } from "../tools/ToolCallCard";
import { MarkdownRenderer } from "../shared/MarkdownRenderer";

interface Props {
  message: ChatMessage;
}

export function AssistantMessage({ message }: Props) {
  return (
    <div className="flex justify-start gap-3 mb-6 animate-fade-in">
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 via-indigo-500 to-blue-500 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-[var(--shadow-xs)] shadow-violet-400/20">
        <span className="text-white text-base font-bold">π</span>
      </div>

      <div className="max-w-[78%] min-w-0">
        {message.thinking && <ThinkingBlock thinking={message.thinking} />}
        {message.content && (
          <div className="text-base leading-relaxed break-words">
            <MarkdownRenderer content={message.content} />
          </div>
        )}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mt-3 space-y-2">
            {message.toolCalls.map((tc) => (
              <ToolCallCard key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
