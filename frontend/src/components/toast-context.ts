import { createContext, useContext } from 'react';

type ToastType = 'success' | 'error' | 'info';

interface ToastContextValue {
  addToast: (message: string, type?: ToastType) => void;
}

export const ToastContext = createContext<ToastContextValue>({
  addToast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

export type { ToastType };
