import React from 'react';
import { useApp } from '../../context/AppContext';
import { CheckCircle2, AlertCircle, Info, AlertTriangle, X, Undo2 } from 'lucide-react';

export function ToastContainer() {
  const { toasts, removeToast } = useApp();

  if (!toasts || toasts.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="System Notifications"
      style={{
        position: 'fixed',
        bottom: '1.25rem',
        right: '1.25rem',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: '0.6rem',
        maxWidth: '380px',
        width: '100%',
        pointerEvents: 'none',
      }}
    >
      {toasts.map((toast) => {
        let borderColor = 'var(--govt-gray-medium)';
        let IconComponent = Info;
        let iconColor = 'var(--govt-blue-primary)';

        if (toast.type === 'success') {
          borderColor = 'var(--govt-success-border, #a7f3d0)';
          IconComponent = CheckCircle2;
          iconColor = 'var(--govt-success, #059669)';
        } else if (toast.type === 'error') {
          borderColor = 'var(--govt-danger-border, #fecaca)';
          IconComponent = AlertCircle;
          iconColor = 'var(--govt-danger, #dc2626)';
        } else if (toast.type === 'warning') {
          borderColor = 'var(--govt-warning-border, #fde68a)';
          IconComponent = AlertTriangle;
          iconColor = 'var(--govt-warning, #d97706)';
        }

        return (
          <div
            key={toast.id}
            role="status"
            style={{
              pointerEvents: 'auto',
              backgroundColor: '#ffffff',
              border: `1px solid ${borderColor}`,
              boxShadow: 'var(--shadow-lg, 0 10px 15px -3px rgba(0, 0, 0, 0.1))',
              borderRadius: 'var(--radius-md, 8px)',
              padding: '0.85rem 1rem',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.75rem',
              animation: 'slideUp 0.2s ease-out',
            }}
          >
            <IconComponent size={18} color={iconColor} style={{ flexShrink: 0, marginTop: '2px' }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <h4
                style={{
                  margin: 0,
                  fontSize: '0.85rem',
                  fontWeight: 700,
                  color: 'var(--govt-gray-title, #0f172a)',
                  lineHeight: 1.3,
                }}
              >
                {toast.title}
              </h4>
              <p
                style={{
                  margin: '0.2rem 0 0',
                  fontSize: '0.775rem',
                  color: 'var(--govt-gray-dark, #64748b)',
                  lineHeight: 1.35,
                }}
              >
                {toast.description}
              </p>

              {toast.undoAction && (
                <button
                  type="button"
                  onClick={() => {
                    toast.undoAction?.();
                    removeToast(toast.id);
                  }}
                  style={{
                    marginTop: '0.5rem',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px',
                    backgroundColor: 'var(--govt-gray-light, #f1f5f9)',
                    border: '1px solid var(--govt-gray-medium, #e2e8f0)',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    color: 'var(--govt-blue-primary, #1d4ed8)',
                    cursor: 'pointer',
                  }}
                >
                  <Undo2 size={13} />
                  <span>{toast.undoLabel || 'Undo'}</span>
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={() => removeToast(toast.id)}
              aria-label="Dismiss notification"
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--govt-gray-dark)',
                cursor: 'pointer',
                padding: '2px',
                lineHeight: 1,
                flexShrink: 0,
              }}
            >
              <X size={15} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

export default ToastContainer;
