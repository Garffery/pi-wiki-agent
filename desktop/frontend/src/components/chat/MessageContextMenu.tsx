import { useEffect, useRef } from "react";
import { api } from "../../services/api";
import { useSessionStore } from "../../stores/sessionStore";

interface Props {
  x: number;
  y: number;
  sessionId: string;
  entryId?: string;
  onClose: () => void;
}

export function MessageContextMenu({ x, y, sessionId, entryId, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const addSession = useSessionStore((s) => s.addSession);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("mousedown", handler);
    window.addEventListener("keydown", keyHandler);
    return () => {
      window.removeEventListener("mousedown", handler);
      window.removeEventListener("keydown", keyHandler);
    };
  }, [onClose]);

  const handleFork = async () => {
    try {
      const result = await api.forkSession(sessionId, entryId);
      addSession(result);
      onClose();
    } catch (e) {
      console.error("Fork failed:", e);
      onClose();
    }
  };

  // Adjust position to stay within viewport
  const adjustedX = Math.min(x, window.innerWidth - 200);
  const adjustedY = Math.min(y, window.innerHeight - 150);

  return (
    <div
      ref={ref}
      className="fixed z-[200] bg-[var(--bg-card)] border border-[var(--border-default)] rounded-xl shadow-[var(--shadow-lg)] py-1 min-w-[180px]"
      style={{ left: adjustedX, top: adjustedY }}
    >
      <div className="px-3 py-1.5 border-b border-[var(--border-subtle)]">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-tertiary)]">
          消息操作
        </span>
      </div>
      <button
        onClick={handleFork}
        className="w-full text-left px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--bg-card-hover)] transition-colors flex items-center gap-2.5"
      >
        <svg className="w-4 h-4 text-[var(--accent-text)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
        </svg>
        {entryId ? "从此处 Fork" : "Fork 当前会话"}
      </button>
      <button
        onClick={onClose}
        className="w-full text-left px-3 py-2 text-sm text-[var(--text-tertiary)] hover:bg-[var(--bg-card-hover)] transition-colors flex items-center gap-2.5"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
        关闭
      </button>
    </div>
  );
}
