import { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="editorial-curtain p-6 text-editorial-ivory">
          <h2 className="text-lg font-semibold mb-2">Something broke.</h2>
          <pre className="text-eyebrow font-mono whitespace-pre-wrap break-all">
            {String(this.state.error)}
          </pre>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 rounded border border-editorial-ivory px-3 py-1.5 text-sm hover:bg-editorial-ivory/10"
          >
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
