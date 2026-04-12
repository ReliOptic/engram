import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';

interface ResizableLayoutProps {
  header: ReactNode;
  leftTop: ReactNode;
  leftBottom: ReactNode;
  center: ReactNode;
  right: ReactNode;
}

const MIN_SIDEBAR = 180;
const MAX_SIDEBAR = 500;
const MIN_CENTER = 400;
const DEFAULT_LEFT = 280;
const DEFAULT_RIGHT = 280;

const STORAGE_KEY = 'zemas-layout-widths';
const COLLAPSE_KEY = 'zemas-layout-collapsed';

function loadWidths(): { left: number; right: number } {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return JSON.parse(stored);
  } catch { /* ignore */ }
  return { left: DEFAULT_LEFT, right: DEFAULT_RIGHT };
}

function saveWidths(left: number, right: number) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ left, right }));
}

function loadCollapsed(): { left: boolean; right: boolean } {
  try {
    const stored = localStorage.getItem(COLLAPSE_KEY);
    if (stored) return JSON.parse(stored);
  } catch { /* ignore */ }
  return { left: false, right: false };
}

function saveCollapsed(left: boolean, right: boolean) {
  localStorage.setItem(COLLAPSE_KEY, JSON.stringify({ left, right }));
}

export function ResizableLayout({ header, leftTop, leftBottom, center, right }: ResizableLayoutProps) {
  const stored = loadWidths();
  const storedCollapsed = loadCollapsed();
  const [leftWidth, setLeftWidth] = useState(stored.left);
  const [rightWidth, setRightWidth] = useState(stored.right);
  const [leftCollapsed, setLeftCollapsed] = useState(storedCollapsed.left);
  const [rightCollapsed, setRightCollapsed] = useState(storedCollapsed.right);
  const [dragging, setDragging] = useState<'left' | 'right' | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const effectiveLeft = leftCollapsed ? 0 : leftWidth;
  const effectiveRight = rightCollapsed ? 0 : rightWidth;

  const handleMouseDown = useCallback((side: 'left' | 'right') => {
    setDragging(side);
  }, []);

  useEffect(() => {
    if (!dragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();

      if (dragging === 'left') {
        const newLeft = Math.max(MIN_SIDEBAR, Math.min(MAX_SIDEBAR, e.clientX - rect.left));
        if (rect.width - newLeft - effectiveRight >= MIN_CENTER) {
          setLeftWidth(newLeft);
          setLeftCollapsed(false);
        }
      } else if (dragging === 'right') {
        const newRight = Math.max(MIN_SIDEBAR, Math.min(MAX_SIDEBAR, rect.right - e.clientX));
        if (rect.width - effectiveLeft - newRight >= MIN_CENTER) {
          setRightWidth(newRight);
          setRightCollapsed(false);
        }
      }
    };

    const handleMouseUp = () => {
      setDragging(null);
      saveWidths(leftWidth, rightWidth);
      saveCollapsed(leftCollapsed, rightCollapsed);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [dragging, effectiveLeft, effectiveRight, leftWidth, rightWidth, leftCollapsed, rightCollapsed]);

  const toggleLeft = useCallback(() => {
    setLeftCollapsed((prev) => {
      const next = !prev;
      saveCollapsed(next, rightCollapsed);
      return next;
    });
  }, [rightCollapsed]);

  const toggleRight = useCallback(() => {
    setRightCollapsed((prev) => {
      const next = !prev;
      saveCollapsed(leftCollapsed, next);
      return next;
    });
  }, [leftCollapsed]);

  // Expose toggle functions for keyboard shortcuts
  useEffect(() => {
    const w = window as unknown as Record<string, unknown>;
    w.__zemasToggleLeft = toggleLeft;
    w.__zemasToggleRight = toggleRight;
    return () => {
      delete w.__zemasToggleLeft;
      delete w.__zemasToggleRight;
    };
  }, [toggleLeft, toggleRight]);

  return (
    <div style={styles.root}>
      {header}
      <div ref={containerRef} style={styles.body}>
        {/* Left sidebar */}
        <aside
          style={{
            ...styles.leftSidebar,
            width: effectiveLeft,
            minWidth: leftCollapsed ? 0 : MIN_SIDEBAR,
            transition: dragging ? 'none' : 'width 0.2s ease',
            overflow: leftCollapsed ? 'hidden' : undefined,
          }}
        >
          {!leftCollapsed && (
            <>
              <div style={styles.leftTop}>{leftTop}</div>
              <div style={styles.leftBottom}>{leftBottom}</div>
            </>
          )}
        </aside>

        {/* Left divider */}
        <div
          style={{
            ...styles.divider,
            ...(dragging === 'left' ? styles.dividerActive : {}),
          }}
          onMouseDown={() => handleMouseDown('left')}
          onDoubleClick={toggleLeft}
        >
          {leftCollapsed && (
            <button onClick={toggleLeft} style={styles.collapseBtn} title="Expand left sidebar">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M4 2L8 6L4 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </button>
          )}
        </div>

        {/* Center */}
        <main style={styles.center}>{center}</main>

        {/* Right divider */}
        <div
          style={{
            ...styles.divider,
            ...(dragging === 'right' ? styles.dividerActive : {}),
          }}
          onMouseDown={() => handleMouseDown('right')}
          onDoubleClick={toggleRight}
        >
          {rightCollapsed && (
            <button onClick={toggleRight} style={styles.collapseBtn} title="Expand right sidebar">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M8 2L4 6L8 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </button>
          )}
        </div>

        {/* Right sidebar */}
        <aside
          style={{
            ...styles.rightSidebar,
            width: effectiveRight,
            minWidth: rightCollapsed ? 0 : MIN_SIDEBAR,
            transition: dragging ? 'none' : 'width 0.2s ease',
            overflow: rightCollapsed ? 'hidden' : undefined,
          }}
        >
          {!rightCollapsed && right}
        </aside>
      </div>

      {/* Overlay to prevent text selection during drag */}
      {dragging && <div style={styles.overlay} />}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  body: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
  },
  leftSidebar: {
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--bg-sidebar)',
    borderRight: '1px solid var(--border-light)',
    overflow: 'hidden',
    flexShrink: 0,
  },
  leftTop: {
    flexShrink: 0,
    borderBottom: '1px solid var(--border-light)',
  },
  leftBottom: {
    flex: 1,
    overflowY: 'auto',
  },
  center: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    background: 'var(--bg-secondary)',
    minWidth: MIN_CENTER,
  },
  rightSidebar: {
    background: 'var(--bg-sidebar)',
    borderLeft: '1px solid var(--border-light)',
    overflowY: 'auto',
    flexShrink: 0,
  },
  divider: {
    width: '4px',
    cursor: 'col-resize',
    background: 'transparent',
    transition: 'background 0.15s',
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    zIndex: 2,
  },
  dividerActive: {
    background: 'var(--zeiss-blue)',
  },
  collapseBtn: {
    position: 'absolute',
    width: '20px',
    height: '40px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--bg-sidebar)',
    border: '1px solid var(--border-light)',
    borderRadius: 'var(--radius-sm)',
    cursor: 'pointer',
    color: 'var(--text-muted)',
    padding: 0,
    zIndex: 3,
  },
  overlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 999,
    cursor: 'col-resize',
  },
};
