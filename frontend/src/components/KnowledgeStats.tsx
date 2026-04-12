import { useEffect, useState } from 'react';

interface KnowledgeData {
  collections: Record<string, number>;
  total_chunks: number;
  cases: { total: number; recent_7d: number };
  sessions_total: number;
}

export function KnowledgeStats() {
  const [data, setData] = useState<KnowledgeData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/knowledge/stats')
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={styles.container}>
        <h3 style={styles.heading}>Knowledge Base</h3>
        <div style={styles.shimmer} />
      </div>
    );
  }

  if (!data) return null;

  const collections = [
    { key: 'manuals', label: 'Manuals / SOPs', icon: '\u{1F4D8}' },
    { key: 'case_records', label: 'Case Records', icon: '\u{1F4CB}' },
    { key: 'weekly', label: 'Weekly Reports', icon: '\u{1F4CA}' },
    { key: 'traces', label: 'Conversation Traces', icon: '\u{1F4AC}' },
  ];

  const hasData = data.total_chunks > 0;

  return (
    <div style={styles.container}>
      <h3 style={styles.heading}>Knowledge Base</h3>

      {!hasData ? (
        <div style={styles.empty}>
          <div style={styles.emptyIcon}>{'\u{1F4DA}'}</div>
          <p style={styles.emptyText}>
            No knowledge data yet. Use DB Builder to import manuals, or start resolving cases to build your knowledge base.
          </p>
        </div>
      ) : (
        <>
          <div style={styles.totalBar}>
            <span style={styles.totalNumber}>{data.total_chunks.toLocaleString()}</span>
            <span style={styles.totalLabel}>total chunks</span>
          </div>

          <div style={styles.grid}>
            {collections.map(({ key, label, icon }) => {
              const count = data.collections[key] || 0;
              return (
                <div key={key} style={styles.statCard}>
                  <div style={styles.statIcon}>{icon}</div>
                  <div style={styles.statInfo}>
                    <span style={styles.statCount}>{count.toLocaleString()}</span>
                    <span style={styles.statLabel}>{label}</span>
                  </div>
                </div>
              );
            })}
          </div>

          {(data.cases.total > 0 || data.sessions_total > 0) && (
            <div style={styles.activitySection}>
              <h4 style={styles.subHeading}>Activity</h4>
              <div style={styles.activityRow}>
                <span style={styles.activityLabel}>Total cases resolved</span>
                <span style={styles.activityValue}>{data.cases.total}</span>
              </div>
              <div style={styles.activityRow}>
                <span style={styles.activityLabel}>Cases this week</span>
                <span style={{
                  ...styles.activityValue,
                  color: data.cases.recent_7d > 0 ? 'var(--accent-green, #4CAF50)' : 'var(--text-muted)',
                }}>
                  {data.cases.recent_7d > 0 ? `+${data.cases.recent_7d}` : '0'}
                </span>
              </div>
              <div style={styles.activityRow}>
                <span style={styles.activityLabel}>Support sessions</span>
                <span style={styles.activityValue}>{data.sessions_total}</span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
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
  shimmer: {
    height: '80px',
    borderRadius: '8px',
    background: 'linear-gradient(90deg, var(--bg-secondary) 25%, var(--bg-primary) 50%, var(--bg-secondary) 75%)',
    backgroundSize: '200% 100%',
    animation: 'shimmer 1.5s infinite',
  },
  empty: {
    textAlign: 'center',
    padding: '20px 8px',
  },
  emptyIcon: {
    fontSize: '32px',
    marginBottom: '8px',
    opacity: 0.5,
  },
  emptyText: {
    fontSize: '12px',
    color: 'var(--text-muted)',
    lineHeight: '1.6',
  },
  totalBar: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '6px',
    marginBottom: '12px',
    padding: '10px 12px',
    borderRadius: '8px',
    background: 'var(--bg-primary)',
    border: '1px solid var(--border-light)',
  },
  totalNumber: {
    fontSize: '22px',
    fontWeight: 700,
    color: 'var(--brand-primary, #141E8C)',
  },
  totalLabel: {
    fontSize: '12px',
    color: 'var(--text-muted)',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '6px',
    marginBottom: '12px',
  },
  statCard: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 10px',
    borderRadius: '6px',
    background: 'var(--bg-primary)',
    border: '1px solid var(--border-light)',
  },
  statIcon: {
    fontSize: '16px',
    flexShrink: 0,
  },
  statInfo: {
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
  },
  statCount: {
    fontSize: '14px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  statLabel: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  activitySection: {
    borderTop: '1px solid var(--border-light)',
    paddingTop: '10px',
  },
  subHeading: {
    fontSize: '11px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    color: 'var(--text-muted)',
    marginBottom: '8px',
  },
  activityRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '4px 0',
  },
  activityLabel: {
    fontSize: '12px',
    color: 'var(--text-secondary)',
  },
  activityValue: {
    fontSize: '13px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
};
