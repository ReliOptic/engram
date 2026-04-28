import { useEffect, useState } from 'react';

interface KnowledgeData {
  collections: Record<string, number>;
  total_chunks: number;
  cases: { total: number; recent_7d: number };
  sessions_total: number;
  growth?: number[];
  recent?: Array<{ kind: string; label: string; t: string }>;
  dreaming?: { linksMade: number; last: string } | null;
}

function MiniSpark({ values, color, width = 86, height = 28 }: { values: number[]; color: string; width?: number; height?: number }) {
  if (!values || values.length < 2) return null;
  const max = Math.max(...values, 1);
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = height - (v / max) * height;
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} fill="none">
      <polyline points={pts} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function BookIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h11a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3V4z" />
      <path d="M4 17a3 3 0 0 1 3-3h11" />
    </svg>
  );
}

function CaseIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
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
      <div style={{ padding: '14px' }}>
        <div style={styles.eyebrowRow}>
          <span style={styles.eyebrow}>KNOWLEDGE</span>
        </div>
        <div style={styles.shimmer} />
      </div>
    );
  }

  if (!data) return null;

  const hasData = data.total_chunks > 0;
  const manualCount = data.collections['manuals'] || 0;
  const caseCount = data.collections['case_records'] || 0;
  const growthValues = data.growth ?? [];
  const recentItems = data.recent ?? [];
  const todayGrowth = growthValues.length > 0 ? growthValues[growthValues.length - 1] : null;

  // Estimate doc count as rough heuristic (chunks / 10)
  const docEstimate = Math.max(1, Math.round(data.total_chunks / 10));

  return (
    <div style={{ padding: '14px' }}>
      <div style={styles.eyebrowRow}>
        <span style={styles.eyebrow}>KNOWLEDGE</span>
        {todayGrowth !== null && todayGrowth > 0 && (
          <span style={styles.eyebrowGrowth}>+{todayGrowth} today</span>
        )}
      </div>

      {!hasData ? (
        <div style={styles.empty}>
          <div style={styles.emptyIcon}>
            <BookIcon size={28} />
          </div>
          <p style={styles.emptyText}>
            No knowledge data yet. Use DB Builder to import manuals, or start resolving cases to build your knowledge base.
          </p>
        </div>
      ) : (
        <>
          {/* Main stats card */}
          <div style={styles.mainCard}>
            <div style={styles.mainCardLeft}>
              <span style={styles.bigNumber}>{data.total_chunks.toLocaleString()}</span>
              <span style={styles.bigSubLabel}>chunks · {docEstimate} docs</span>
            </div>
            <div style={styles.mainCardRight}>
              <MiniSpark
                values={growthValues.length >= 2 ? growthValues.slice(-8) : [manualCount, caseCount, data.total_chunks]}
                color="var(--brand-primary, #141E8C)"
              />
            </div>
          </div>

          {/* 2-column grid: Manuals + Cases */}
          <div style={styles.grid}>
            <div style={styles.gridCard}>
              <span style={{ color: 'var(--agent-finder, #0D7A5F)', display: 'flex' }}>
                <BookIcon size={16} />
              </span>
              <span style={styles.gridLabel}>Manuals</span>
              <span style={styles.gridCount}>{manualCount.toLocaleString()}</span>
              <span style={styles.gridSub}>docs</span>
            </div>
            <div style={styles.gridCard}>
              <span style={{ color: 'var(--brand-link, #1D4ED8)', display: 'flex' }}>
                <CaseIcon size={16} />
              </span>
              <span style={styles.gridLabel}>Cases</span>
              <span style={styles.gridCount}>{caseCount.toLocaleString()}</span>
              <span style={styles.gridSub}>records</span>
            </div>
          </div>

          {/* Recently learned */}
          {recentItems.length > 0 && (
            <div style={styles.recentSection}>
              <span style={styles.sectionEyebrow}>RECENTLY LEARNED</span>
              <div style={styles.recentList}>
                {recentItems.slice(0, 5).map((item, i) => (
                  <div key={i} style={styles.recentItem}>
                    <span style={{
                      color: item.kind === 'manual' ? 'var(--agent-finder, #0D7A5F)' : 'var(--brand-link, #1D4ED8)',
                      display: 'flex',
                      flexShrink: 0,
                    }}>
                      {item.kind === 'manual' ? <BookIcon size={12} /> : <CaseIcon size={12} />}
                    </span>
                    <span style={styles.recentLabel}>{item.label}</span>
                    <span style={styles.recentTime}>{relativeTime(item.t)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Dreaming status */}
          {data.dreaming !== undefined && (
            <div style={styles.dreamingCard}>
              <div style={styles.dreamingIconWrap}>
                <MoonIcon />
              </div>
              <div style={styles.dreamingInfo}>
                <span style={styles.dreamingTitle}>Dreaming</span>
                <span style={styles.dreamingSub}>
                  {data.dreaming
                    ? `+${data.dreaming.linksMade} links · last ${relativeTime(data.dreaming.last)}`
                    : 'Not yet run'}
                </span>
              </div>
            </div>
          )}
        </>
      )}
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
  eyebrowGrowth: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--accent-green, #16A34A)',
    fontVariantNumeric: 'tabular-nums',
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
    display: 'flex',
    justifyContent: 'center',
    marginBottom: '8px',
    opacity: 0.4,
    color: 'var(--text-muted)',
  },
  emptyText: {
    fontSize: '12px',
    color: 'var(--text-muted)',
    lineHeight: '1.6',
  },
  // Main stats card
  mainCard: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 12px',
    borderRadius: 'var(--radius-md, 6px)',
    background: 'var(--surface-panel, var(--bg-primary))',
    border: '1px solid var(--border-hairline, var(--border-light))',
    boxShadow: 'var(--shadow-xs, 0 1px 2px rgba(0,0,0,0.05))',
    marginBottom: '8px',
  },
  mainCardLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  bigNumber: {
    fontSize: '22px',
    fontWeight: 700,
    fontFamily: 'monospace',
    color: 'var(--text-primary)',
    lineHeight: 1,
  },
  bigSubLabel: {
    fontSize: '11px',
    color: 'var(--text-muted)',
  },
  mainCardRight: {
    display: 'flex',
    alignItems: 'center',
  },
  // 2-col grid
  grid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '6px',
    marginBottom: '10px',
  },
  gridCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
    padding: '8px 10px',
    borderRadius: 'var(--radius-md, 6px)',
    background: 'var(--surface-panel, var(--bg-primary))',
    border: '1px solid var(--border-hairline, var(--border-light))',
    boxShadow: 'var(--shadow-xs, 0 1px 2px rgba(0,0,0,0.05))',
  },
  gridLabel: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.4px',
  },
  gridCount: {
    fontSize: '18px',
    fontWeight: 700,
    fontFamily: 'monospace',
    color: 'var(--text-primary)',
    lineHeight: 1,
  },
  gridSub: {
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
  // Recently learned
  recentSection: {
    marginBottom: '10px',
  },
  sectionEyebrow: {
    fontSize: '9px',
    fontWeight: 700,
    letterSpacing: '0.8px',
    textTransform: 'uppercase' as const,
    color: 'var(--text-muted)',
    display: 'block',
    marginBottom: '6px',
  },
  recentList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  recentItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  recentLabel: {
    fontSize: '11px',
    color: 'var(--text-secondary)',
    flex: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  recentTime: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    flexShrink: 0,
    fontVariantNumeric: 'tabular-nums',
  },
  // Dreaming card
  dreamingCard: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '8px 10px',
    borderRadius: 'var(--radius-md, 6px)',
    border: '1px dashed var(--border-soft, var(--border-light))',
  },
  dreamingIconWrap: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    background: 'var(--ask-bg, rgba(99,102,241,0.1))',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    color: 'var(--agent-reviewer, #6366F1)',
  },
  dreamingInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1px',
    minWidth: 0,
  },
  dreamingTitle: {
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  dreamingSub: {
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
};
