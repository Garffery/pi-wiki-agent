import { useState, useEffect, useRef, useCallback } from "react";
import { useSessionStore } from "../../stores/sessionStore";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function SessionSwitcher({ open, onClose }: Props) {
  const { sessions, activeSessionId, setActiveSession } = useSessionStore();
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const filtered = sessions.filter((s) => {
    if (!query) return true;
    const q = query.toLowerCase();
    const name = s.label || s.cwd?.split(/[/\\]/).pop() || "";
    return name.toLowerCase().includes(q)
      || s.session_id.toLowerCase().includes(q)
      || s.cwd?.toLowerCase().includes(q);
  });

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const handleSelect = useCallback((id: string) => {
    setActiveSession(id);
    onClose();
  }, [setActiveSession, onClose]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (filtered[selectedIndex]) {
          handleSelect(filtered[selectedIndex].session_id);
        }
        break;
      case "Escape":
        onClose();
        break;
    }
  }, [filtered, selectedIndex, handleSelect, onClose]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const selected = el.querySelector(`[data-index="${selectedIndex}"]`);
    if (selected) {
      selected.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIndex]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div
        ref={containerRef}
        className="relative w-full max-w-lg bg-[var(--bg-card)] border border-[var(--border-default)] rounded-2xl shadow-[var(--shadow-lg)] overflow-hidden"
      >
        {/* Search header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border-subtle)]">
          <svg className="w-5 h-5 text-[var(--text-tertiary)] flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="搜索会话名称、ID 或路径..."
            className="flex-1 bg-transparent border-none text-base text-[var(--text-primary)] placeholder-[var(--text-placeholder)] focus:outline-none py-1"
          />
          <kbd className="px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-tertiary)] bg-[var(--bg-main)] rounded border border-[var(--border-default)]">
            ESC
          </kbd>
        </div>

        {/* Session list */}
        <div className="max-h-72 overflow-y-auto py-2">
          {filtered.length === 0 ? (
            <div className="px-4 py-12 text-center">
              <p className="text-sm text-[var(--text-tertiary)]">
                {sessions.length === 0 ? "暂无会话" : "未找到匹配的会话"}
              </p>
            </div>
          ) : (
            filtered.map((s, i) => {
              const isActive = s.session_id === activeSessionId;
              const isSelected = i === selectedIndex;
              const name = s.label || s.cwd?.split(/[/\\]/).pop() || "未命名";

              return (
                <button
                  key={s.session_id}
                  data-index={i}
                  onClick={() => handleSelect(s.session_id)}
                  className={`w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors ${
                    isSelected
                      ? "bg-[var(--accent-soft)]"
                      : "hover:bg-[var(--bg-card-hover)]"
                  }`}
                >
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                    isActive
                      ? "bg-[var(--accent)] shadow-[0_0_8px_var(--accent-glow)]"
                      : "bg-[var(--text-tertiary)]/30"
                  }`} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-[var(--text-primary)] truncate">
                      {name}
                      {isActive && (
                        <span className="ml-2 text-[10px] text-[var(--accent-text)] font-normal">当前</span>
                      )}
                    </div>
                    <div className="text-xs text-[var(--text-tertiary)] mt-0.5 flex items-center gap-1.5">
                      <span className="truncate">{s.model?.split("/").pop() || "无模型"}</span>
                      {s.message_count != null && s.message_count > 0 && (
                        <>
                          <span>·</span>
                          <span>{s.message_count} 条消息</span>
                        </>
                      )}
                      {s.cwd && (
                        <>
                          <span>·</span>
                          <span className="truncate max-w-[180px]">{s.cwd}</span>
                        </>
                      )}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-[var(--border-subtle)] flex items-center gap-3 text-[11px] text-[var(--text-tertiary)]">
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-[var(--bg-main)] border border-[var(--border-default)] text-[10px]">↑↓</kbd> 导航
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-[var(--bg-main)] border border-[var(--border-default)] text-[10px]">Enter</kbd> 选择
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-[var(--bg-main)] border border-[var(--border-default)] text-[10px]">Esc</kbd> 关闭
          </span>
        </div>
      </div>
    </div>
  );
}
