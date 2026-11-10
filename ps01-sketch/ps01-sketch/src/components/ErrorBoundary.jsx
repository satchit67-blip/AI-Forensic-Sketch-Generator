import { Component } from 'react';
import { AlertTriangle } from 'lucide-react';

// Catches render errors so a crash shows a readable message instead of a blank screen.
// variant="page" wraps the whole app; the default wraps a single panel.
export default class ErrorBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error: error || new Error('Unknown error') }; }
  componentDidCatch(error, info) { console.error('UI crashed:', error, info?.componentStack); }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const page = this.props.variant === 'page';
    return (
      <section role="alert" className={`glass flex flex-col items-center justify-center gap-3 p-8 text-center ${page ? 'mx-auto my-16 max-w-xl' : ''}`}>
        <AlertTriangle className="text-red-400" size={36} />
        <p className="font-mono text-sm text-red-300">{page ? 'The app hit an unexpected error' : 'This panel hit an error'}</p>
        <p className="max-w-md break-words font-mono text-[11px] text-slate-400">{String(error.message || error)}</p>
        {page ? (
          <button className="btn" onClick={() => window.location.assign('/studio')}>Back to studio</button>
        ) : (
          <button className="btn" onClick={() => this.setState({ error: null })}>Reload panel</button>
        )}
      </section>
    );
  }
}
