import { useUIStore } from "../../stores/uiStore";

const S = { lineHeight: 3.0 } as const;

export function SettingsPanel() {
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const theme = useUIStore((s) => s.theme);
  const setTheme = useUIStore((s) => s.setTheme);

  const shortcuts = [
    ["Ctrl + P", "切换模型"],
    ["Ctrl + L", "清空对话"],
    ["Ctrl + T", "切换思考级别"],
    ["Enter", "发送消息"],
    ["Shift + Enter", "插入换行"],
    ["Escape", "中止 / 关闭菜单"],
    ["/", "打开命令面板"],
  ];

  return (
    <div className="h-full overflow-y-auto">
      <div className="py-12" style={{ paddingLeft: 0, paddingRight: 64 }}>
        {/* Header */}
        <div className="flex items-center justify-between mb-12">
          <h2 className="text-2xl font-semibold text-[var(--text-primary)] tracking-tight" style={S}>
            设置
          </h2>
          <button
            onClick={() => setSettingsOpen(false)}
            className="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            返回
          </button>
        </div>

        {/* Appearance */}
        <section className="mb-16">
          <h3
            className="text-sm font-semibold uppercase tracking-widest text-[var(--text-tertiary)] mb-6"
            style={S}
          >
            外观
          </h3>
          <div className="flex items-center justify-between py-6">
            <div className="min-w-0">
              <div className="text-lg font-medium text-[var(--text-primary)]" style={S}>主题</div>
              <div className="text-base text-[var(--text-tertiary)] mt-2" style={S}>
                切换浅色与深色模式
              </div>
            </div>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value as "dark" | "light")}
              className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-base font-medium text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] appearance-none cursor-pointer hover:border-[var(--border-strong)] transition-colors flex-shrink-0 ml-4"
            >
              <option value="light">浅色</option>
              <option value="dark">深色</option>
            </select>
          </div>
        </section>

        {/* Keyboard Shortcuts */}
        <section>
          <h3
            className="text-sm font-semibold uppercase tracking-widest text-[var(--text-tertiary)] mb-6"
            style={S}
          >
            快捷键
          </h3>
          <div className="divide-y divide-[var(--border-subtle)]">
            {shortcuts.map(([key, desc]) => (
              <div key={key} className="flex items-center justify-between py-6 gap-6 min-w-0">
                <span className="text-base text-[var(--text-secondary)] truncate min-w-0" style={S}>{desc}</span>
                <kbd className="text-base font-mono font-medium text-[var(--text-primary)] whitespace-nowrap flex-shrink-0 text-right" style={S}>
                  {key}
                </kbd>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
