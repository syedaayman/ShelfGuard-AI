import { useEffect } from 'react';
import { CheckCircle2, AlertCircle, X } from 'lucide-react';

export default function Toast({ message, type = 'success', onClose, duration = 4000 }) {
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => {
      onClose();
    }, duration);
    return () => clearTimeout(timer);
  }, [message, duration, onClose]);

  if (!message) return null;

  return (
    <div className="toast-container">
      <div className={`toast ${type === 'error' ? 'toast-error' : 'toast-success'}`}>
        {type === 'error' ? (
          <AlertCircle size={20} style={{ color: 'var(--status-expired)', flexShrink: 0 }} />
        ) : (
          <CheckCircle2 size={20} style={{ color: 'var(--accent-primary)', flexShrink: 0 }} />
        )}
        <div style={{ flex: 1, fontSize: '0.875rem' }}>{message}</div>
        <button onClick={onClose} className="btn-ghost" style={{ padding: '2px', cursor: 'pointer' }}>
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
