import { createContext, type ReactNode, useCallback, useContext, useState } from 'react';

type ToastType = 'success' | 'error' | 'info';

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  addToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({
  addToast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

let toastId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      {toasts.length > 0 && (
        <div style={styles.container}>
          {toasts.map((toast) => (
            <div
              key={toast.id}
              style={{
                ...styles.toast,
                borderLeft: `4px solid ${COLORS[toast.type]}`,
              }}
            >
              <span style={styles.message}>{toast.message}</span>
              <button
                style={styles.close}
                onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      )}
    </ToastContext.Provider>
  );
}

const COLORS: Record<ToastType, string> = {
  success: 'var(--color-success)',
  error: 'var(--color-error)',
  info: 'var(--zeiss-blue)',
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    position: 'fixed',
    bottom: '20px',
    right: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    zIndex: 9999,
    maxWidth: '360px',
  },
  toast: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 14px',
    background: 'var(--bg-primary)',
    borderRadius: 'var(--radius-md)',
    boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
    animation: 'slideIn 0.2s ease-out',
  },
  message: {
    flex: 1,
    fontSize: '13px',
    color: 'var(--text-primary)',
    lineHeight: '1.4',
  },
  close: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: '16px',
    color: 'var(--text-muted)',
    padding: '0 2px',
    lineHeight: 1,
    flexShrink: 0,
  },
};
