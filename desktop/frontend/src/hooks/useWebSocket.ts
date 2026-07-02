import { useEffect, useRef, useCallback } from "react";
import { useChatStore } from "../stores/chatStore";
import { createSessionStream } from "../services/websocket";
import type { AgentEvent } from "../types/events";

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleEvent = useChatStore((s) => s.handleEvent);

  const connect = useCallback(() => {
    if (!sessionId) return;

    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = createSessionStream(
      sessionId,
      (event: AgentEvent) => {
        handleEvent(event);
      },
      () => {
        // Auto-reconnect after 2s
        reconnectRef.current = setTimeout(() => {
          connect();
        }, 2000);
      }
    );

    wsRef.current = ws;
  }, [sessionId, handleEvent]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  const send = useCallback(
    (data: object) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(data));
      }
    },
    []
  );

  return { send };
}
