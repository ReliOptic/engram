import { useEffect, useRef, useState } from 'react';
import { useToast } from '../Toast';
import { Skeleton } from '../Skeleton';

export function VectorDBSettings() {
  const [stats, setStats] = useState<Record<string, number> | null>(null);
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { addToast } = useToast();

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
  importBtn: {
    padding: '8px 20px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-medium)',
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'var(--font-family)',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
};
