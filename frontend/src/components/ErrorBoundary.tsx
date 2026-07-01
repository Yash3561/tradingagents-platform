import { Component, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="min-h-screen bg-bg-base flex items-center justify-center p-6">
          <div className="card p-8 max-w-md w-full text-center">
            <AlertTriangle size={40} className="text-warn mx-auto mb-4" />
            <h2 className="text-lg font-bold text-white mb-2">Something went wrong</h2>
            <p className="text-sm text-slate-400 mb-2">
              {this.state.error?.message ?? "An unexpected error occurred"}
            </p>
            <p className="text-xs text-slate-600 mb-6 font-mono bg-bg-elevated rounded p-2 text-left break-words">
              {this.state.error?.stack?.split("\n")[0]}
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="flex items-center gap-2 mx-auto px-5 py-2.5 bg-accent hover:bg-accent/90 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <RefreshCw size={14} />
              Reload App
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
