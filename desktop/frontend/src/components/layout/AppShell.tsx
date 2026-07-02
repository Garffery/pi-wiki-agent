import { type ReactNode } from "react";

interface Props {
  sidebar: ReactNode;
  header: ReactNode;
  children: ReactNode;
  footer: ReactNode;
  input: ReactNode;
}

export function AppShell({ sidebar, header, children, footer, input }: Props) {
  return (
    <div className="flex h-full bg-[var(--bg-app)]">
      {sidebar}
      <div className="flex-1 flex flex-col min-w-0 bg-[var(--bg-main)]">
        {header}
        <div className="flex-1 overflow-hidden relative">{children}</div>
        {footer}
        {input}
      </div>
    </div>
  );
}
