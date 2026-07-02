import { useEffect, useRef } from "react";
import { getCommandCompletions } from "../../commands/slashCommands";

interface Props {
  filter: string;
  onSelect: (cmd: string) => void;
  onClose: () => void;
}

export function SlashCommandMenu({ filter, onSelect, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const commands = getCommandCompletions();
  const filtered = commands.filter(
    (c) =>
      c.name.toLowerCase().includes(filter.toLowerCase()) ||
      c.description.toLowerCase().includes(filter.toLowerCase())
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [onClose]);

  if (filtered.length === 0) return null;

  return (
    <div
      ref={ref}
      className="absolute bottom-full left-4 right-4 mb-2 bg-[var(--bg-card)] border border-[var(--border-default)] rounded-2xl shadow-[var(--shadow-lg)] max-h-72 overflow-y-auto z-50"
    >
      <div className="px-4 py-2.5 border-b border-[var(--border-subtle)]">
        <span className="text-xs font-semibold uppercase tracking-widest text-[var(--text-tertiary)]">
          命令
</span>
      </div>
      {filtered.map((cmd, i) => (
        <button
          key={cmd.name}
          onClick={() => onSelect(cmd.name)}
          className={`w-full text-left px-4 py-3 hover:bg-[var(--bg-card-hover)] transition-colors flex items-center gap-3 ${
            i < filtered.length - 1 ? "border-b border-[var(--border-subtle)]" : ""
          }`}
        >
          <code className="text-sm font-semibold text-[var(--accent-text)] bg-[var(--accent-soft)] px-2 py-0.5 rounded-md min-w-[84px] text-center">
            {cmd.name}
          </code>
          <span className="text-sm text-[var(--text-tertiary)] truncate">{cmd.description}</span>
        </button>
      ))}
    </div>
  );
}
