import { useEffect, useState } from "react";
import { useSessionStore } from "../../stores/sessionStore";
import { useUIStore } from "../../stores/uiStore";
import { api } from "../../services/api";
import { SessionTree } from "../sessions/SessionTree";

export function Sidebar() {
  const {
    sessions, activeSessionId, searchQuery,
    setSessions, setActiveSession, addSession, removeSession, setSearchQuery,
  } = useSessionStore();
  const { sidebarOpen, setSettingsOpen } = useUIStore();
  const [treeMode, setTreeMode] = useState(false);

  useEffect(() => {
    api.listSessions().then(setSessions).catch(console.error);
  }, [setSessions]);

  if (!sidebarOpen) return null;

  const handleNewSession = async () => {
    try {
      const info = await api.createSession();
      addSession(info);
    } catch (e) {
      console.error(e);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteSession(id);
      removeSession(id);
    } catch (e) {
      console.error(e);
    }
  };

  const formatTime = (ts?: number) => {
    if (!ts) return "";
    const now = Date.now();
    const diff = now - ts;
    if (diff < 60_000) return "刚刚";
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}分钟前`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}小时前`;
    return new Date(ts).toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  };

  const filtered = sessions.filter((s) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const name = s.label || (s.cwd?.split(/[/\\]/).pop()) || "未命名";
    return name.toLowerCase().includes(q)
      || s.session_id.toLowerCase().includes(q)
      || s.model?.toLowerCase().includes(q);
  });

  return (
    <div className="w-64 bg-[var(--bg-sidebar)] border-r border-[var(--border-default)] flex flex-col flex-shrink-0">
      {/* Brand header */}
      <div className="px-4 pt-5 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 via-indigo-500 to-blue-500 flex items-center justify-center text-white text-lg font-bold shadow-[var(--shadow-sm)]">
              π
            </div>
            <span className="font-semibold text-lg text-[var(--text-primary)] tracking-tight">Pi</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setTreeMode(!treeMode)}
              className={`w-7 h-7 flex items-center justify-center rounded-lg transition-all text-xs font-bold ${
                treeMode
                  ? "bg-[var(--accent-soft)] text-[var(--accent-text)]"
                  : "bg-[var(--bg-card)] hover:bg-[var(--bg-card-hover)] text-[var(--text-tertiary)]"
              }`}
              title={treeMode ? "列表视图" : "树形视图"}
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M3 7l4-4 4 4M3 17l4 4 4-4M7 3v18" />
              </svg>
            </button>
            <button
              onClick={handleNewSession}
              className="w-8 h-8 flex items-center justify-center rounded-xl bg-[var(--bg-card)] hover:bg-[var(--bg-card-hover)] border border-[var(--border-default)] text-[var(--text-secondary)] hover:text-[var(--accent)] transition-all shadow-[var(--shadow-xs)]"
              title="新建会话"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <div className="relative">
          <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-tertiary)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索会话..."
            className="w-full bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg py-1.5 pl-8 pr-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-placeholder)] focus:outline-none focus:border-[var(--accent)]/30 transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 flex items-center justify-center rounded text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Section label */}
      <div className="px-4 pb-1.5 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-widest text-[var(--text-tertiary)]">
          {treeMode ? "对话树" : (searchQuery ? `搜索结果 (${filtered.length})` : "会话")}
        </span>
        {treeMode && activeSessionId && (
          <button
            onClick={() => setTreeMode(false)}
            className="text-[10px] text-[var(--accent-text)] hover:text-[var(--accent-strong)] transition-colors"
          >
            返回列表
          </button>
        )}
      </div>

      {/* Content: Tree or Session list */}
      {treeMode ? (
        activeSessionId ? (
          <SessionTree
            sessionId={activeSessionId}
            onNavigate={(entryId) => {
              api.executeCommand(activeSessionId, "/tree", entryId).catch(console.error);
            }}
          />
        ) : (
          <div className="flex-1 flex items-center justify-center px-4">
            <p className="text-xs text-[var(--text-tertiary)] text-center">
              请先选择一个会话以查看对话树
            </p>
          </div>
        )
      ) : (
        <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
          {filtered.map((s) => {
            const isActive = s.session_id === activeSessionId;
            const name = s.label || s.cwd?.split(/[/\\]/).pop() || "未命名";

            return (
              <button
                key={s.session_id}
                onClick={() => setActiveSession(s.session_id)}
                className={`group relative w-full text-left px-3 py-2.5 rounded-[var(--radius-sm)] transition-all duration-[var(--transition-fast)] ${
                  isActive
                    ? "bg-[var(--accent-soft)] ring-1 ring-[var(--accent)]/15"
                    : "hover:bg-[var(--bg-card-hover)]"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 transition-colors ${
                    isActive
                      ? "bg-[var(--accent)] shadow-[0_0_8px_var(--accent-glow)]"
                      : s.is_streaming
                        ? "bg-green-400 animate-pulse"
                        : "bg-[var(--text-tertiary)]/30"
                  }`} />

                  <div className="min-w-0 flex-1">
                    <div className={`text-sm font-medium truncate transition-colors ${
                      isActive ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                    }`}>
                      {name}
                    </div>
                    <div className="text-xs text-[var(--text-tertiary)] mt-0.5 flex items-center gap-1.5 min-w-0">
                      <span className="truncate">{s.model?.split("/").pop() || "无模型"}</span>
                      {s.message_count != null && s.message_count > 0 && (
                        <>
                          <span className="opacity-40 flex-shrink-0">·</span>
                          <span className="flex-shrink-0">{s.message_count}</span>
                        </>
                      )}
                    </div>
                    {s.updated_at && (
                      <div className="text-[10px] text-[var(--text-tertiary)]/60 mt-0.5">
                        {formatTime(s.updated_at)}
                      </div>
                    )}
                  </div>

                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(s.session_id);
                    }}
                    className="opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center rounded-md text-[var(--text-tertiary)] hover:text-[var(--error)] hover:bg-[var(--error-soft)] transition-all flex-shrink-0"
                    title="删除会话"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </span>
                </div>
              </button>
            );
          })}

          {filtered.length === 0 && searchQuery && (
            <div className="px-3 py-8 text-center">
              <p className="text-sm text-[var(--text-tertiary)]">未找到匹配的会话</p>
            </div>
          )}

          {filtered.length === 0 && !searchQuery && (
            <div className="px-3 py-12 text-center">
              <p className="text-sm text-[var(--text-tertiary)] mb-3">暂无会话</p>
              <button
                onClick={handleNewSession}
                className="text-sm font-medium text-[var(--accent-text)] hover:text-[var(--accent-strong)] transition-colors"
              >
                创建第一个会话
              </button>
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="px-2 py-2 border-t border-[var(--border-default)]">
        <button
          onClick={() => setSettingsOpen(true)}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-[var(--radius-sm)] text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-card-hover)] transition-all"
        >
          <svg className="w-4 h-4 text-[var(--text-tertiary)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          设置
        </button>
      </div>
    </div>
  );
}
