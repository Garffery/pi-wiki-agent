import { useState, useRef, useCallback } from "react";
import { api } from "../../services/api";
import { useSessionStore } from "../../stores/sessionStore";
import { useChatStore } from "../../stores/chatStore";
import { useUIStore } from "../../stores/uiStore";
import { SlashCommandMenu } from "./SlashCommandMenu";

export function ChatInput() {
  const [value, setValue] = useState("");
  const [showCommands, setShowCommands] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const addMessage = useChatStore((s) => s.addMessage);
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);

  const handleSubmit = useCallback(async () => {
    const text = value.trim();
    if (!text || !activeSessionId) return;

    if (text.startsWith("/")) {
      const spaceIdx = text.indexOf(" ");
      const cmd = spaceIdx > 0 ? text.slice(0, spaceIdx) : text;
      const args = spaceIdx > 0 ? text.slice(spaceIdx + 1) : "";

      if (cmd === "/clear") {
        useChatStore.getState().clearMessages();
        setValue("");
        return;
      }
      if (cmd === "/settings") {
        setSettingsOpen(true);
        setValue("");
        return;
      }

      try {
        const result = await api.executeCommand(activeSessionId, cmd, args);
        if (result.status === "unknown_command") {
          addMessage({
            id: `sys-${Date.now()}`,
            role: "system",
            content: `未知命令：${cmd}。输入 /help 查看可用命令。`,
            timestamp: Date.now(),
          });
        }
      } catch (e) {
        console.error(e);
      }
      setValue("");
      return;
    }

    addMessage({
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: Date.now(),
    });

    setValue("");

    try {
      await api.sendPrompt(activeSessionId, text);
    } catch (e) {
      console.error(e);
      addMessage({
        id: `err-${Date.now()}`,
        role: "system",
        content: `错误：${e instanceof Error ? e.message : "发送失败"}`,
        timestamp: Date.now(),
      });
    }
  }, [value, activeSessionId, addMessage, setSettingsOpen]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!isStreaming) handleSubmit();
      }
      if (e.key === "Escape") {
        setShowCommands(false);
        if (isStreaming && activeSessionId) {
          api.abort(activeSessionId).catch(console.error);
        }
      }
      if (e.key === "/" && value === "") {
        setShowCommands(true);
      }
    },
    [handleSubmit, isStreaming, activeSessionId, value]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const v = e.target.value;
      setValue(v);
      setShowCommands(v === "/");
    },
    []
  );

  const selectCommand = useCallback((cmd: string) => {
    setValue(cmd + " ");
    setShowCommands(false);
    textareaRef.current?.focus();
  }, []);

  return (
    <div className="relative bg-[var(--bg-main)] border-t border-[var(--border-default)]">
      {showCommands && (
        <SlashCommandMenu
          filter={value}
          onSelect={selectCommand}
          onClose={() => setShowCommands(false)}
        />
      )}
      <div className="py-3" style={{ paddingLeft: 0, paddingRight: 64 }}>
        <div className={`
          flex items-end gap-2 bg-[var(--bg-input)] rounded-2xl border px-4 py-2.5
          transition-all duration-[var(--transition-fast)]
          shadow-[var(--shadow-xs)]
          ${isStreaming
            ? "border-[var(--border-default)] opacity-80"
            : "border-[var(--border-default)] focus-within:border-[var(--accent)]/30 focus-within:shadow-[var(--shadow-sm)]"
          }
        `}>
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={
              isStreaming
                ? "AI 正在回复..."
                : "输入消息..."
            }
            rows={1}
            className="flex-1 bg-transparent border-none text-base text-[var(--text-primary)] placeholder-[var(--text-placeholder)] resize-none focus:outline-none py-1 leading-relaxed"
            style={{ maxHeight: "160px" }}
            onInput={(e) => {
              const el = e.target as HTMLTextAreaElement;
              el.style.height = "auto";
              el.style.height = Math.min(el.scrollHeight, 160) + "px";
            }}
          />

          <div className="flex items-center gap-1.5 flex-shrink-0">
            {!value.trim() && !isStreaming && (
              <div className="hidden sm:flex items-center gap-0.5 text-sm text-[var(--text-tertiary)] mr-1">
                <kbd className="px-1 py-0.5 rounded-[var(--radius-xs)] bg-[var(--bg-card)] border border-[var(--border-default)] text-xs font-medium">
                  /
                </kbd>
                <span className="opacity-40">命令</span>
              </div>
            )}
            {isStreaming ? (
              <button
                onClick={() => activeSessionId && api.abort(activeSessionId).catch(console.error)}
                className="w-9 h-9 flex items-center justify-center rounded-xl bg-[var(--error-soft)] hover:bg-[var(--error)]/20 text-[var(--error)] transition-all"
                title="停止生成"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={!value.trim()}
                className="w-9 h-9 flex items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 hover:from-violet-600 hover:to-blue-600 disabled:from-[var(--border-default)] disabled:to-[var(--border-default)] disabled:text-[var(--text-tertiary)] text-white transition-all shadow-[var(--shadow-xs)] disabled:shadow-none"
                title="发送"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                    d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
