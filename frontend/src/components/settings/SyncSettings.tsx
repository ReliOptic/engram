import { useCallback, useEffect, useState } from 'react';

interface SyncStatus {
  enabled: boolean;
  server_url: string | null;
  online: boolean | null;
  pending_events: number;
  status: string;
}

export function SyncSettings() {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const resp = await fetch('/api/sync/status');
      if (resp.ok) setStatus(await resp.json());
    } catch { /* offline */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  if (loading) return <p>Loading sync status...</p>;
  if (!status) return <p>Could not load sync status.</p>;

  return (
    <div>
      <h2 style={{ margin: '0 0 8px' }}>Sync</h2>
      <p style={{ color: '#666', margin: '0 0 24px', fontSize: '14px' }}>
        Sync cases and knowledge with a team server on your LAN.
      </p>

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <tbody>
          <Row label="Status">
            <StatusBadge status={status.status} />
          </Row>
          <Row label="Server URL">
            {status.server_url || <span style={{ color: '#999' }}>Not configured (standalone mode)</span>}
          </Row>
          <Row label="Pending Events">
            {status.pending_events}
          </Row>
        </tbody>
      </table>

      {!status.enabled && (
        <div style={{
          marginTop: '24px', padding: '16px', background: '#f5f5f5',
          borderRadius: '8px', fontSize: '13px', color: '#666',
        }}>
          <strong>Standalone mode.</strong> To enable sync, add to your <code>.env</code>:
          <pre style={{
            background: '#e8e8e8', padding: '8px', borderRadius: '4px',
            marginTop: '8px', fontSize: '12px',
          }}>
{`SYNC_SERVER_URL=http://192.168.1.100:9000
SYNC_DEVICE_NAME=My-PC`}
          </pre>
          Then restart the backend.
        </div>
      )}

      {status.enabled && (
        <div style={{ marginTop: '24px', display: 'flex', gap: '8px' }}>
          <button
            onClick={async () => {
              await fetch('/api/sync/push', { method: 'POST' });
              fetchStatus();
            }}
            style={btnStyle}
          >
            Push Now
          </button>
          <button
            onClick={async () => {
              await fetch('/api/sync/pull', { method: 'POST' });
              fetchStatus();
            }}
            style={btnStyle}
          >
            Pull Now
          </button>
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <tr style={{ borderBottom: '1px solid #eee' }}>
      <td style={{ padding: '10px 12px', fontWeight: 500, width: '160px', color: '#555' }}>
        {label}
      </td>
      <td style={{ padding: '10px 12px' }}>{children}</td>
    </tr>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, { bg: string; fg: string }> = {
    synced: { bg: '#E8F5E9', fg: '#2E7D32' },
    pending: { bg: '#FFF3E0', fg: '#E65100' },
    offline: { bg: '#FFEBEE', fg: '#C62828' },
    disabled: { bg: '#F5F5F5', fg: '#999' },
  };
  const c = colors[status] || colors.disabled;
  return (
    <span style={{
      background: c.bg, color: c.fg, padding: '4px 12px',
      borderRadius: '12px', fontSize: '12px', fontWeight: 600,
    }}>
      {status}
    </span>
  );
}

const btnStyle: React.CSSProperties = {
  padding: '8px 20px',
  background: 'var(--zeiss-blue)',
  color: 'white',
  border: 'none',
  borderRadius: '4px',
  cursor: 'pointer',
  fontWeight: 600,
  fontSize: '13px',
};
