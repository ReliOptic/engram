import type { ReactNode } from 'react';

interface LayoutProps {
  header: ReactNode;
  leftTop: ReactNode;
  leftBottom: ReactNode;
  center: ReactNode;
  right: ReactNode;
}

export function Layout({ header, leftTop, leftBottom, center, right }: LayoutProps) {
  return (
    <div style={styles.root}>
      {header}
      <div style={styles.body}>
        {/* Left sidebar: Agents + History */}
        <aside style={styles.leftSidebar}>
          <div style={styles.leftTop}>{leftTop}</div>
          <div style={styles.leftBottom}>{leftBottom}</div>
        </aside>

        {/* Center: Chat timeline + input */}
        <main style={styles.center}>{center}</main>

        {/* Right sidebar: Sources */}
        <aside style={styles.rightSidebar}>{right}</aside>
      </div>
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
    display: 'grid',
    gridTemplateColumns: 'var(--sidebar-width) 1fr var(--sidebar-width)',
    overflow: 'hidden',
  },
  leftSidebar: {
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--bg-sidebar)',
    borderRight: '1px solid var(--border-light)',
    overflow: 'hidden',
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
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    background: 'var(--bg-secondary)',
  },
  rightSidebar: {
    background: 'var(--bg-sidebar)',
    borderLeft: '1px solid var(--border-light)',
    overflowY: 'auto',
  },
};
