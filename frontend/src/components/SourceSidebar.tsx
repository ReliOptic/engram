import type { ChunkDetail, SourceRef } from '../types';

interface SourceSidebarProps {
  sources: SourceRef[];
  activeChunk?: ChunkDetail | null;
  onCloseChunk?: () => void;
  onSourceClick?: (sourceId: string) => void;
}

const TYPE_ICONS: Record<string, string> = {
  manual: '📘',
  case: '📋',
  weekly: '📊',
};

const COLLECTION_LABELS: Record<string, string> = {
  case_records: 'Case Record',
  traces: 'Trace',
  weekly: 'Weekly Report',
  manuals: 'Manual',
};

export function SourceSidebar({ sources, activeChunk, onCloseChunk, onSourceClick }: SourceSidebarProps) {
  if (activeChunk) {
    return <ChunkDetailPanel chunk={activeChunk} onClose={onCloseChunk} />;
  }

  if (sources.length === 0) return null;

  return (
    <div style={styles.sidebar}>
      <h3 style={styles.heading}>Sources Referenced</h3>
      <div style={styles.list}>
        {sources.map((src) => (
          <div key={src.id} style={styles.item} onClick={() => onSourceClick?.(src.id)}>
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

function ChunkDetailPanel({ chunk, onClose }: { chunk: ChunkDetail; onClose?: () => void }) {
  const collectionLabel = COLLECTION_LABELS[chunk.collection] ?? chunk.collection;
  const metaEntries = Object.entries(chunk.metadata).filter(
    ([k, v]) => k !== '_' && v !== null && v !== undefined && v !== '',
  );

  return (
    <div style={styles.sidebar}>
      <div style={styles.detailHeader}>
        <h3 style={styles.heading}>{collectionLabel}</h3>
        {onClose && (
          <button onClick={onClose} style={styles.backBtn} aria-label="Back to sources">
            ← 목록
          </button>
        )}
      </div>
      <div style={styles.detailId}>{chunk.id}</div>
      <div style={styles.detailDocument}>{chunk.document}</div>
      {metaEntries.length > 0 && (
        <div style={styles.metaTable}>
          {metaEntries.map(([k, v]) => (
            <div key={k} style={styles.metaRow}>
              <span style={styles.metaKey}>{k}</span>
              <span style={styles.metaVal}>{String(v)}</span>
            </div>
          ))}
        </div>
      )}
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
  // Chunk detail panel
  detailHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '12px',
  },
  backBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: '11px',
    color: 'var(--brand-link)',
    fontWeight: 600,
    padding: '0 2px',
    lineHeight: 1,
  },
  detailId: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    fontFamily: 'monospace',
    marginBottom: '10px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  detailDocument: {
    fontSize: '12px',
    lineHeight: '1.6',
    color: 'var(--text-primary)',
    whiteSpace: 'pre-wrap',
    background: 'var(--bg-secondary)',
    borderRadius: 'var(--radius-md)',
    padding: '10px',
    marginBottom: '12px',
    maxHeight: '300px',
    overflowY: 'auto',
  },
  metaTable: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  metaRow: {
    display: 'flex',
    gap: '8px',
    fontSize: '11px',
  },
  metaKey: {
    color: 'var(--text-muted)',
    fontWeight: 600,
    minWidth: '80px',
    flexShrink: 0,
  },
  metaVal: {
    color: 'var(--text-primary)',
    wordBreak: 'break-all',
  },
};
