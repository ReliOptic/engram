import { useEffect } from 'react';

interface ShortcutHandlers {
  onNewChat?: () => void;
  onFocusInput?: () => void;
  onToggleLeftSidebar?: () => void;
  onToggleRightSidebar?: () => void;
  onStop?: () => void;
}

export function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const ctrl = e.ctrlKey || e.metaKey;

      if (ctrl && e.key === 'n') {
        e.preventDefault();
        handlers.onNewChat?.();
      }

      if (ctrl && e.key === 'k') {
        e.preventDefault();
        handlers.onFocusInput?.();
      }

      if (ctrl && e.key === ',') {
        e.preventDefault();
        window.location.href = '/settings';
      }

      if (ctrl && e.key === 'b') {
        e.preventDefault();
        handlers.onToggleLeftSidebar?.();
      }

      if (ctrl && e.key === '.') {
        e.preventDefault();
        handlers.onToggleRightSidebar?.();
      }

      if (e.key === 'Escape') {
        handlers.onStop?.();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handlers]);
}
