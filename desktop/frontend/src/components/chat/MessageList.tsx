import type { ChatMessage } from "../../types/events";
import { MessageBubble } from "./MessageBubble";

interface Props {
  messages: ChatMessage[];
}

export function MessageList({ messages }: Props) {
  return (
    <div className="space-y-1">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
    </div>
  );
}
