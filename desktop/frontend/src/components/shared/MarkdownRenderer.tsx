import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  content: string;
}

export function MarkdownRenderer({ content }: Props) {
  return (
    <div className="markdown-body text-base leading-relaxed text-[var(--text-primary)] break-words min-w-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const isInline = !className;
            if (isInline) {
              return (
                <code
                  className="bg-[var(--bg-input)] text-[var(--accent-text)] px-1.5 py-0.5 rounded-[var(--radius-xs)] text-sm font-medium border border-[var(--border-default)]"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre({ children }) {
            return <pre className="overflow-x-auto rounded-xl shadow-[var(--shadow-xs)]">{children}</pre>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
