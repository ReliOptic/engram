import { useEffect, useRef, useState } from 'react';
import { useToast } from '../toast-context';
import { Skeleton } from '../Skeleton';

export function VectorDBSettings() {
  const [stats, setStats] = useState<Record<string, number> | null>(null);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { addToast } = useToast();

  const [dreamingStatus, setDreamingStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [dreamingResult, setDreamingResult] = useState<string | null>(null);

  const handleDreaming = async () => {
    setDreamingStatus('running');
    setDreamingResult(null);
    try {
      const resp = await fetch('/api/dreaming/trigger', { method: 'POST' });
      const data = await resp.json();
      if (data.ok) {
        setDreamingStatus('done');
        setDreamingResult(
          `완료: 패턴 ${data.rem_patterns}개 · 그래프 노드 ${data.graph_nodes}개`
        );
        fetchStats();
      } else {
        setDreamingStatus('error');
        setDreamingResult(data.error || 'Unknown error');
      }
    } catch {
      setDreamingStatus('error');
      setDreamingResult('Network error');
    }
  };

  const handleExport = async () => {
    const resp = await fetch('/api/settings/vectordb/export');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'engram_vectordb_export.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const fetchStats = () => {
    fetch('/api/settings/vectordb/stats')
      .then((r) => r.json())
      .then((d: Record<string, number>) => setStats(d))
      .catch(() => addToast('Failed to load VectorDB stats', 'error'));
  };

  useEffect(() => {
    fetchStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setImporting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const resp = await fetch('/api/settings/vectordb/import', {
        method: 'POST',
        body: formData,
      });
      const data = await resp.json();
      if (data.ok) {
        addToast('VectorDB imported successfully', 'success');
        fetchStats();
      } else {
        addToast(`Import failed: ${data.error || 'Unknown error'}`, 'error');
      }
    } catch {
      addToast('Network error during import', 'error');
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <div>
      <h2 style={styles.heading}>VectorDB Collections</h2>
      <p style={styles.description}>ChromaDB collection statistics and data import.</p>

      {!stats ? (
        <Skeleton height="36px" count={4} gap="8px" />
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Collection</th>
              <th style={styles.th}>Chunks</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(stats).map(([name, count]) => (
              <tr key={name}>
                <td style={styles.td}>
                  <span style={styles.collName}>{name}</span>
                </td>
                <td style={styles.td}>
                  <span style={styles.count}>{count.toLocaleString()}</span>
                </td>
              </tr>
            ))}
            <tr>
              <td style={{ ...styles.td, fontWeight: 600 }}>Total</td>
              <td style={{ ...styles.td, fontWeight: 600 }}>
                {Object.values(stats).reduce((a, b) => a + b, 0).toLocaleString()}
              </td>
            </tr>
          </tbody>
        </table>
      )}

      <div style={styles.importSection}>
        <h3 style={styles.subheading}>Import Data</h3>
        <p style={styles.description}>
          Upload a .zip or .tar.gz archive containing ChromaDB data.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".zip,.tar,.tar.gz,.tgz"
          style={{ display: 'none' }}
          onChange={handleImport}
        />
        <button
          style={styles.importBtn}
          onClick={() => fileRef.current?.click()}
          disabled={importing}
        >
          {importing ? 'Importing...' : 'Import Archive'}
        </button>
      </div>

      <div style={styles.actionSection}>
        <h3 style={styles.subheading}>Knowledge Dreaming</h3>
        <p style={styles.description}>
          지식 정제 파이프라인 (중복 제거 → 패턴 감지 → 그래프 구축). 매일 밤 자동 실행됩니다.
        </p>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button
            style={{ ...styles.importBtn, background: dreamingStatus === 'running' ? '#e0e0e0' : undefined }}
            onClick={handleDreaming}
            disabled={dreamingStatus === 'running'}
          >
            {dreamingStatus === 'running' ? '실행 중...' : '지금 실행'}
          </button>
          {dreamingResult && (
            <span style={{ fontSize: '12px', color: dreamingStatus === 'error' ? '#ef4444' : '#15803d' }}>
              {dreamingResult}
            </span>
          )}
        </div>
      </div>

      <div style={{ ...styles.importSection, marginTop: '16px' }}>
        <h3 style={styles.subheading}>Export Data</h3>
        <p style={styles.description}>모든 컬렉션을 JSON으로 내보냅니다 (백업 / 이전용).</p>
        <button style={styles.importBtn} onClick={handleExport}>
          Export JSON
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  heading: {
    fontSize: '16px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: '4px',
  },
  subheading: {
    fontSize: '14px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: '4px',
  },
  description: {
    fontSize: '13px',
    color: 'var(--text-secondary)',
    marginBottom: '16px',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    marginBottom: '24px',
  },
  th: {
    textAlign: 'left',
    padding: '8px 12px',
    fontSize: '11px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    color: 'var(--text-muted)',
    borderBottom: '1px solid var(--border-light)',
  },
  td: {
    padding: '8px 12px',
    borderBottom: '1px solid var(--border-light)',
    fontSize: '13px',
  },
  collName: {
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
    color: 'var(--text-primary)',
  },
  count: {
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
    fontWeight: 600,
    color: 'var(--brand-primary)',
  },
  importSection: {
    padding: '16px',
    background: 'var(--bg-primary)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-light)',
  },
  actionSection: {
    padding: '16px',
    background: 'var(--bg-primary)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-light)',
    marginTop: '16px',
  },
  importBtn: {
    padding: '8px 20px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-medium)',
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'var(--font-sans)',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
};
