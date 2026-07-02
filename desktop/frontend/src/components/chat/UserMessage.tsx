import type { ChatMessage } from "../../types/events";

interface Props {
  message: ChatMessage;
}

export function UserMessage({ message }: Props) {
  return (
    <div className="flex justify-end gap-3 mb-6 animate-fade-in">
      <div className="max-w-[72%] min-w-0">
        <div className="text-base leading-relaxed whitespace-pre-wrap break-all text-[var(--text-primary)]">
          {message.content}
        </div>
      </div>
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-400 via-indigo-400 to-blue-400 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-[var(--shadow-xs)]">
        <span className="text-white text-sm font-bold">Y</span>
      </div>
    </div>
  );
}
