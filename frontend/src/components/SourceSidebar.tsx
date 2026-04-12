import type { SourceRef } from '../types';

interface SourceSidebarProps {
  sources: SourceRef[];
}

const TYPE_ICONS: Record<string, string> = {
  manual: '📘',
  case: '📋',
  weekly: '📊',
};

export function SourceSidebar({ sources }: SourceSidebarProps) {
  if (sources.length === 0) return null;

  return (
    <div style={styles.sidebar}>
      <h3 style={styles.heading}>Sources Referenced</h3>
      <div style={styles.list}>
        {sources.map((src) => (
          <div key={src.id} style={styles.item}>
            <span style={styles.icon}>{TYPE_ICONS[src.type] ?? '📄'}</span>
            <div style={styles.itemInfo}>
              <span style={styles.itemTitle}>{src.title}</span>
              <span style={styles.itemMeta}>
                {src.type} &middot; {Math.round(src.relevance * 100)}% match
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    padding: '16px',
  },
  heading: {
    fontSize: '12px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    color: 'var(--text-muted)',
    marginBottom: '12px',
  },
  emptyText: {
    fontSize: '12px',
    color: 'var(--text-muted)',
    lineHeight: '1.6',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  item: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '8px',
    padding: '8px 10px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--bg-primary)',
    border: '1px solid var(--border-light)',
    cursor: 'pointer',
  },
  icon: {
    fontSize: '16px',
    flexShrink: 0,
    marginTop: '1px',
  },
  itemInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    minWidth: 0,
  },
  itemTitle: {
    fontSize: '12px',
    fontWeight: 500,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  itemMeta: {
    fontSize: '11px',
    color: 'var(--text-muted)',
  },
};
