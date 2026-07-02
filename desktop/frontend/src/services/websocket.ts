/** WebSocket client for streaming agent events */

import type { AgentEvent } from "../types/events";

export type EventHandler = (event: AgentEvent) => void;

export function createSessionStream(
  sessionId: string,
  onEvent: EventHandler,
  onClose?: () => void
): WebSocket {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const host = window.location.host;
  const url = `${protocol}://${host}/api/sessions/${sessionId}/stream`;

  const ws = new WebSocket(url);

  ws.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data);
      onEvent(data as AgentEvent);
    } catch {
      // Ignore malformed messages
    }
  };

  ws.onclose = () => {
    onClose?.();
  };

  return ws;
}
