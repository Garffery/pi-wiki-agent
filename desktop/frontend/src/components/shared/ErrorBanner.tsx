interface Props {
  message: string;
  onDismiss?: () => void;
}

export function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <div className="bg-[var(--error-soft)] border border-[var(--error)]/20 rounded-2xl px-4 py-3 m-3 flex items-center justify-between gap-3 shadow-[var(--shadow-xs)]">
      <div className="flex items-center gap-2.5">
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--error)] flex-shrink-0" />
        <span className="text-base text-[var(--text-primary)]">{message}</span>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors w-6 h-6 flex items-center justify-center rounded-lg hover:bg-[var(--bg-card-hover)]"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}
