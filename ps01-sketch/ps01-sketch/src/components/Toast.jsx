import { AlertCircle, AlertTriangle, CheckCircle2, X } from 'lucide-react';

export default function Toast({ toast, onClose }) {
  if (!toast) return null;

  const isError = toast.type === 'error';
  const isWarning = toast.type === 'warning';

  const bgBorder = isError
    ? 'border-red-500/60 bg-red-950/90 text-red-100 shadow-red-950/50'
    : isWarning
    ? 'border-amber-500/60 bg-amber-950/90 text-amber-100 shadow-amber-950/50'
    : 'border-nexus-cyan/60 bg-nexus-950/90 text-nexus-cyan shadow-nexus-950/50';

  const Icon = isError ? AlertCircle : isWarning ? AlertTriangle : CheckCircle2;

  return (
    <div
      role="alert"
      className={`fixed bottom-6 right-6 z-50 flex max-w-lg items-start gap-3 rounded-xl border p-4 shadow-2xl backdrop-blur-lg transition-all duration-300 animate-in fade-in slide-in-from-bottom-3 ${bgBorder}`}
    >
      <Icon size={20} className="mt-0.5 shrink-0" />
      <div className="flex-1 text-xs leading-relaxed">
        <p className="font-mono font-semibold tracking-wide uppercase text-[11px]">
          {toast.title || (isError ? 'API Error' : isWarning ? 'Fallback Active' : 'Operation Complete')}
        </p>
        <p className="mt-0.5 opacity-90">{toast.message}</p>
      </div>
      <button
        onClick={onClose}
        className="rounded-lg p-1 opacity-70 hover:opacity-100 hover:bg-white/10 transition-colors"
        aria-label="Dismiss notification"
      >
        <X size={15} />
      </button>
    </div>
  );
}
