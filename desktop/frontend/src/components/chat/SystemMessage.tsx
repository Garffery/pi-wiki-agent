import type { ChatMessage } from "../../types/events";

interface Props {
  message: ChatMessage;
}

export function SystemMessage({ message }: Props) {
  return (
    <div className="flex justify-center mb-4 animate-fade-in">
      <span className="px-3 py-1 text-sm font-medium text-[var(--text-tertiary)]">
        {message.content}
      </span>
    </div>
  );
}
