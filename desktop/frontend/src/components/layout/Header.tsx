import { useSessionStore } from "../../stores/sessionStore";
import { useUIStore } from "../../stores/uiStore";

export function Header() {
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const sessions = useSessionStore((s) => s.sessions);
  const { sidebarOpen, toggleSidebar } = useUIStore();
  const activeSession = sessions.find((s) => s.session_id === activeSessionId);

  return (
    <div className="h-12 bg-[var(--bg-main)] border-b border-[var(--border-default)] flex items-center gap-3 flex-shrink-0 overflow-hidden" style={{ paddingLeft: 0, paddingRight: 64 }}>
      <button
        onClick={toggleSidebar}
        className="w-8 h-8 flex items-center justify-center rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card-hover)] transition-all flex-shrink-0"
        title="切换侧栏"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d={sidebarOpen
              ? "M11 19l-7-7 7-7m8 14l-7-7 7-7"
              : "M13 5l7 7-7 7M5 5l7 7-7 7"} />
        </svg>
      </button>

      <div className="flex-1 min-w-0 flex items-center gap-2">
        {activeSession ? (
          <span className="text-base font-medium text-[var(--text-primary)] truncate">
            {activeSession.cwd?.split(/[/\\]/).pop() || "未命名"}
          </span>
        ) : (
          <span className="text-base font-medium text-[var(--text-secondary)]">Pi Desktop</span>
        )}
      </div>

      {activeSession && (
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[var(--accent-soft)] border border-[var(--accent)]/10 max-w-[180px] flex-shrink-0" title={activeSession.model}>
          <div className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] flex-shrink-0" />
          <span className="text-sm font-medium text-[var(--accent-text)] truncate">
            {activeSession.model?.split("/").pop() || "无模型"}
          </span>
        </div>
      )}
    </div>
  );
}
