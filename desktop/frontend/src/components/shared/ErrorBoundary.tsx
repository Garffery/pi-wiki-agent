import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex items-center justify-center h-full p-8 bg-[var(--bg-app)]">
          <div className="bg-[var(--bg-card)] border border-[var(--border-default)] rounded-2xl p-8 max-w-md w-full text-center shadow-[var(--shadow-lg)]">
            <div className="w-14 h-14 mx-auto mb-5 rounded-2xl bg-[var(--error-soft)] flex items-center justify-center">
              <svg className="w-6 h-6 text-[var(--error)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-2 tracking-tight">
              出错了
            </h2>
            <p className="text-base text-[var(--text-secondary)] mb-6 leading-relaxed">
              {this.state.error?.message || "发生了未知错误"}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-br from-violet-500 to-blue-500 hover:from-violet-600 hover:to-blue-600 text-white text-base font-medium rounded-xl transition-all shadow-[var(--shadow-xs)]"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              重试
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
