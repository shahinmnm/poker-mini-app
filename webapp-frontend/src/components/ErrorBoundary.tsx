import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      error,
      errorInfo: null,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({
      error,
      errorInfo,
    });
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div style={{
          padding: '2rem',
          textAlign: 'center',
          color: 'var(--text, #e6e8ef)',
          background: 'var(--bg, #0e0f12)',
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
        }}>
          <h2 style={{ color: 'var(--error, #ef4444)', marginBottom: '1rem' }}>
            Something went wrong
          </h2>
          <p style={{ marginBottom: '1rem', color: 'var(--text-dim, #b6bbc8)' }}>
            The app encountered an error. Please try refreshing.
          </p>
          {this.state.error && (
            <details style={{
              marginTop: '1rem',
              padding: '1rem',
              background: 'var(--panel, #15171c)',
              borderRadius: '8px',
              maxWidth: '600px',
              width: '100%',
              textAlign: 'left',
            }}>
              <summary style={{ cursor: 'pointer', marginBottom: '0.5rem' }}>
                Error Details
              </summary>
              <pre style={{
                fontSize: '12px',
                overflow: 'auto',
                color: 'var(--text-dim, #b6bbc8)',
              }}>
                {this.state.error.toString()}
                {this.state.errorInfo?.componentStack}
              </pre>
            </details>
          )}
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null, errorInfo: null });
              window.location.reload();
            }}
            style={{
              marginTop: '1rem',
              padding: '0.75rem 1.5rem',
              background: 'var(--brand, #9b87f5)',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: '600',
            }}
          >
            Reload App
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

