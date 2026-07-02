import { useState, useCallback } from "react";
import type { ChatMessage } from "../../types/events";
import { UserMessage } from "./UserMessage";
import { AssistantMessage } from "./AssistantMessage";
import { SystemMessage } from "./SystemMessage";
import { MessageContextMenu } from "./MessageContextMenu";
import { useSessionStore } from "../../stores/sessionStore";

interface Props {
  message: ChatMessage;
}

interface ContextMenuState {
  x: number;
  y: number;
}

export function MessageBubble({ message }: Props) {
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY });
  }, []);

  const renderMessage = () => {
    switch (message.role) {
      case "user":
        return <UserMessage message={message} />;
      case "assistant":
        return <AssistantMessage message={message} />;
      case "system":
        return <SystemMessage message={message} />;
      default:
        return null;
    }
  };

  return (
    <>
      <div onContextMenu={handleContextMenu}>
        {renderMessage()}
      </div>
      {contextMenu && activeSessionId && (
        <MessageContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          sessionId={activeSessionId}
          entryId={message.entry_id}
          onClose={() => setContextMenu(null)}
        />
      )}
    </>
  );
}
