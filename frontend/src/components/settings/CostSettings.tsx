import { useEffect, useState } from 'react';
import { Skeleton } from '../Skeleton';

interface CostRow {
  model: string;
  call_count: number;
  total_tokens: number;
  total_cost_usd: number;
}

interface CostSummary {
  by_model: CostRow[];
  total_cost_usd: number;
}

export function CostSettings() {
  const [data, setData] = useState<CostSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/costs/summary')
      .then((r) => r.json())
      .then((d: CostSummary) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <Skeleton height="40px" count={3} gap="8px" />;
  if (!data) return <p style={{ color: 'var(--text-muted)' }}>Failed to load cost data.</p>;

  return (
    <div>
      <h2 style={styles.heading}>LLM Cost Tracking</h2>
      <p style={styles.description}>에이전트별 LLM API 사용량 및 비용 요약입니다.</p>

      <div style={styles.totalCard}>
        <span style={styles.totalLabel}>누적 비용</span>
        <span style={styles.totalValue}>${data.total_cost_usd.toFixed(4)}</span>
      </div>

      {data.by_model.length === 0 ? (
        <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '16px' }}>
          아직 기록된 API 호출이 없습니다. 에이전트가 실행되면 여기에 표시됩니다.
        </p>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Model</th>
              <th style={styles.th}>Calls</th>
              <th style={styles.th}>Tokens</th>
              <th style={styles.th}>Cost (USD)</th>
            </tr>
          </thead>
          <tbody>
            {data.by_model.map((row) => (
              <tr key={row.model}>
                <td style={styles.td}><span style={styles.mono}>{row.model}</span></td>
                <td style={styles.td}>{row.call_count.toLocaleString()}</td>
                <td style={styles.td}>{row.total_tokens.toLocaleString()}</td>
                <td style={{ ...styles.td, fontWeight: 600 }}>${row.total_cost_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  heading: { fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' },
  description: { fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' },
  totalCard: {
    display: 'flex', alignItems: 'baseline', gap: '10px',
    padding: '14px 16px', background: 'var(--bg-primary)',
    borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)',
    marginBottom: '20px',
  },
  totalLabel: { fontSize: '13px', color: 'var(--text-muted)' },
  totalValue: { fontSize: '24px', fontWeight: 700, color: 'var(--brand-primary)' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: {
    textAlign: 'left', padding: '8px 12px', fontSize: '11px', fontWeight: 600,
    textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-muted)',
    borderBottom: '1px solid var(--border-light)',
  },
  td: { padding: '8px 12px', borderBottom: '1px solid var(--border-light)', fontSize: '13px' },
  mono: { fontFamily: 'var(--font-mono)', fontSize: '12px' },
};
