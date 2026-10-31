import React from 'react';
import { useApp } from '../../context/AppContext';
import { X, Keyboard } from 'lucide-react';

export function KeyboardShortcutsModal() {
  const { isShortcutsModalOpen, setIsShortcutsModalOpen } = useApp();

  if (!isShortcutsModalOpen) return null;

  const shortcuts = [
    { key: 'j', desc: 'Navigate down to the next evidence row in Review Queue' },
    { key: 'k', desc: 'Navigate up to the previous evidence row' },
    { key: 'a', desc: 'Approve selected evidence item' },
    { key: 'r', desc: 'Reject selected evidence item' },
    { key: 'f', desc: 'Flag selected evidence for on-site physical inspection' },
    { key: 'Enter', desc: 'Open deep Evidence Inspector for selected item' },
    { key: 'Cmd/Ctrl + K', desc: 'Open Global Command Palette & Search' },
    { key: '?', desc: 'Toggle this Keyboard Shortcuts Helper modal' },
    { key: 'ESC', desc: 'Close open modal, drawer, or dialog' },
  ];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="keyboard-shortcuts-title"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
        backgroundColor: 'rgba(15, 23, 42, 0.6)',
        backdropFilter: 'blur(3px)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) setIsShortcutsModalOpen(false);
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '520px',
          backgroundColor: '#ffffff',
          borderRadius: 'var(--radius-lg, 12px)',
          border: '1px solid var(--govt-gray-medium, #e2e8f0)',
          boxShadow: 'var(--shadow-xl, 0 20px 25px -5px rgba(0, 0, 0, 0.2))',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '1rem 1.25rem',
            borderBottom: '1px solid var(--govt-gray-medium, #e2e8f0)',
            backgroundColor: 'var(--govt-gray-off-white, #f8fafc)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Keyboard size={18} color="var(--govt-blue-primary, #1d4ed8)" />
            <h3
              id="keyboard-shortcuts-title"
              style={{
                margin: 0,
                fontSize: '0.95rem',
                fontWeight: 700,
                color: 'var(--govt-gray-title, #0f172a)',
              }}
            >
              High-Velocity Reviewer Shortcuts
            </h3>
          </div>
          <button
            type="button"
            onClick={() => setIsShortcutsModalOpen(false)}
            aria-label="Close keyboard shortcuts"
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--govt-gray-dark)',
              cursor: 'pointer',
              padding: '4px',
            }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ padding: '1.25rem', maxHeight: '70vh', overflowY: 'auto' }}>
          <p
            style={{
              margin: '0 0 1rem',
              fontSize: '0.8rem',
              color: 'var(--govt-gray-dark, #64748b)',
              lineHeight: 1.4,
            }}
          >
            Institutional reviewer shortcuts for rapid evidence processing without mouse clicks.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {shortcuts.map((s) => (
              <div
                key={s.key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '1rem',
                  padding: '0.5rem 0.25rem',
                  borderBottom: '1px solid var(--govt-gray-light, #f1f5f9)',
                }}
              >
                <span style={{ fontSize: '0.825rem', color: 'var(--govt-gray-text, #1e293b)' }}>
                  {s.desc}
                </span>
                <kbd
                  style={{
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px',
                    backgroundColor: 'var(--govt-gray-light, #f1f5f9)',
                    border: '1px solid var(--govt-gray-medium, #e2e8f0)',
                    fontFamily: 'var(--font-family-mono, monospace)',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    color: 'var(--govt-gray-title, #0f172a)',
                    flexShrink: 0,
                  }}
                >
                  {s.key}
                </kbd>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default KeyboardShortcutsModal;
