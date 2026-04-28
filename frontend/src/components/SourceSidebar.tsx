import type { ChunkDetail, SourceRef } from '../types';

interface SourceSidebarProps {
  sources: SourceRef[];
  activeChunk?: ChunkDetail | null;
  onCloseChunk?: () => void;
  onSourceClick?: (sourceId: string) => void;
}

const COLLECTION_LABELS: Record<string, string> = {
  case_records: 'Case Record',
  traces: 'Trace',
  weekly: 'Weekly Report',
  manuals: 'Manual',
};

function BookIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h11a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3V4z" />
      <path d="M4 17a3 3 0 0 1 3-3h11" />
    </svg>
  );
}

function CaseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

function ArrowLeftIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 12H5M11 5l-7 7 7 7" />
    </svg>
  );
}

function ProbBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ height: 4, background: 'var(--border-hairline, #e5e7eb)', borderRadius: 999, flex: 1 }}>
      <div style={{ height: '100%', width: `${value * 100}%`, background: color, borderRadius: 999 }} />
    </div>
  );
}

function sourceIcon(type: string) {
  if (type === 'manual') return <BookIcon />;
  return <CaseIcon />;
}

function sourceColor(type: string): string {
  if (type === 'manual') return 'var(--agent-finder, #0D7A5F)';
  return 'var(--brand-link, #1D4ED8)';
}

function sourceTypeLabel(type: string): string {
  if (type === 'manual') return 'MANUAL';
  if (type === 'case') return 'CASE';
  if (type === 'weekly') return 'WEEKLY';
  return type.toUpperCase();
}

export function SourceSidebar({ sources, activeChunk, onCloseChunk, onSourceClick }: SourceSidebarProps) {
  if (activeChunk) {
    return <ChunkDetailPanel chunk={activeChunk} onClose={onCloseChunk} />;
  }

  if (sources.length === 0) return null;

  return (
    <div style={{ padding: '14px' }}>
      <div style={styles.eyebrowRow}>
        <span style={styles.eyebrow}>SOURCES CITED</span>
        <span style={styles.eyebrowCount}>{sources.length} this case</span>
      </div>
      <div style={styles.list}>
        {sources.map((src) => {
          const color = sourceColor(src.type);
          return (
            <button
              key={src.id}
              style={styles.item}
              onClick={() => onSourceClick?.(src.id)}
              aria-label={`View source: ${src.title}`}
            >
              <div style={styles.itemRow1}>
                <span style={{ color, display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                  {sourceIcon(src.type)}
                </span>
                <span style={{ ...styles.typeLabel, color }}>{sourceTypeLabel(src.type)}</span>
                <span style={styles.sourceId}>{src.id.slice(0, 12)}</span>
              </div>
              <div style={styles.itemRow2}>{src.title}</div>
              <div style={styles.itemRow3}>{src.type} · chunk</div>
              <div style={styles.itemRow4}>
                <span style={styles.relevanceLabel}>RELEVANCE</span>
                <ProbBar value={src.relevance} color={color} />
                <span style={styles.relevanceScore}>{Math.round(src.relevance * 100)}%</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ChunkDetailPanel({ chunk, onClose }: { chunk: ChunkDetail; onClose?: () => void }) {
  const collectionLabel = COLLECTION_LABELS[chunk.collection] ?? chunk.collection;
  const metaEntries = Object.entries(chunk.metadata).filter(
    ([k, v]) => k !== '_' && v !== null && v !== undefined && v !== '',
  );
  const isManual = chunk.collection === 'manuals';
  const color = isManual ? 'var(--agent-finder, #0D7A5F)' : 'var(--brand-link, #1D4ED8)';

  return (
    <div style={{ padding: '14px' }}>
      {onClose && (
        <button onClick={onClose} style={styles.backBtn} aria-label="Back to sources">
          <ArrowLeftIcon />
          <span>Back to sources</span>
        </button>
      )}
      <div style={styles.detailCard}>
        <div style={styles.detailCardHeader}>
          <span style={{ color, display: 'flex', alignItems: 'center', flexShrink: 0 }}>
            {isManual ? <BookIcon /> : <CaseIcon />}
          </span>
          <span style={{ ...styles.typeLabel, color }}>{collectionLabel.toUpperCase()}</span>
          <span style={styles.detailId}>{chunk.id}</span>
        </div>
        <div style={styles.detailTitle}>{chunk.metadata.title as string || chunk.id}</div>
        {metaEntries.length > 0 && (
          <div style={styles.detailMeta}>
            {metaEntries.slice(0, 3).map(([k, v]) => (
              <span key={k} style={styles.detailMetaItem}>
                <span style={styles.detailMetaKey}>{k}</span>
                <span style={styles.detailMetaVal}>{String(v)}</span>
              </span>
            ))}
          </div>
        )}
        <div style={styles.snippet}>{chunk.document}</div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  eyebrowRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '10px',
  },
  eyebrow: {
    fontSize: '9px',
    fontWeight: 700,
    letterSpacing: '0.8px',
    textTransform: 'uppercase',
    color: 'var(--text-muted)',
  },
  eyebrowCount: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    fontVariantNumeric: 'tabular-nums',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  item: {
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    padding: '8px 10px',
    borderRadius: 'var(--radius-md, 6px)',
    background: 'var(--surface-panel, var(--bg-primary))',
    border: '1px solid var(--border-hairline, var(--border-light))',
    boxShadow: 'var(--shadow-xs, 0 1px 2px rgba(0,0,0,0.05))',
    cursor: 'pointer',
    textAlign: 'left',
  },
  itemRow1: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
  },
  typeLabel: {
    fontSize: '9px',
    fontWeight: 700,
    letterSpacing: '0.6px',
    textTransform: 'uppercase',
    flex: 1,
  },
  sourceId: {
    fontSize: '10px',
    fontFamily: 'monospace',
    color: 'var(--text-muted)',
  },
  itemRow2: {
    fontSize: '12.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  itemRow3: {
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
  itemRow4: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    marginTop: '2px',
  },
  relevanceLabel: {
    fontSize: '9px',
    fontWeight: 700,
    letterSpacing: '0.5px',
    color: 'var(--text-muted)',
    flexShrink: 0,
  },
  relevanceScore: {
    fontSize: '11px',
    fontFamily: 'monospace',
    color: 'var(--text-secondary)',
    flexShrink: 0,
  },
  // Detail panel
  backBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    background: 'var(--surface-sunken, var(--bg-secondary))',
    border: 'none',
    borderRadius: 'var(--radius-sm, 4px)',
    cursor: 'pointer',
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--brand-link, #1D4ED8)',
    padding: '4px 8px',
    marginBottom: '10px',
  },
  detailCard: {
    background: 'var(--surface-panel, var(--bg-primary))',
    border: '1px solid var(--border-hairline, var(--border-light))',
    boxShadow: 'var(--shadow-xs, 0 1px 2px rgba(0,0,0,0.05))',
    borderRadius: 'var(--radius-md, 6px)',
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  detailCardHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  detailId: {
    fontSize: '10px',
    fontFamily: 'monospace',
    color: 'var(--text-muted)',
    marginLeft: 'auto',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
    maxWidth: '120px',
  },
  detailTitle: {
    fontSize: '14px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  detailMeta: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '6px',
  },
  detailMetaItem: {
    display: 'flex',
    gap: '4px',
    fontSize: '11px',
    color: 'var(--text-muted)',
  },
  detailMetaKey: {
    fontWeight: 600,
  },
  detailMetaVal: {
    color: 'var(--text-secondary)',
    wordBreak: 'break-all' as const,
  },
  snippet: {
    background: 'var(--surface-sunken, var(--bg-secondary))',
    borderLeft: '3px solid var(--brand-primary, #141E8C)',
    borderRadius: '0 var(--radius-sm, 4px) var(--radius-sm, 4px) 0',
    padding: '8px 10px',
    fontSize: '13px',
    color: 'var(--text-secondary)',
    lineHeight: '1.6',
    whiteSpace: 'pre-wrap',
    maxHeight: '280px',
    overflowY: 'auto',
  },
};
