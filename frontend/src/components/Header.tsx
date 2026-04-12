import { Link } from 'react-router-dom';

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';
type SyncStatus = 'disabled' | 'synced' | 'pending' | 'offline';

interface HeaderProps {
  wsStatus: ConnectionStatus;
  syncStatus?: SyncStatus;
  syncPending?: number;
}

export function Header({ wsStatus, syncStatus, syncPending }: HeaderProps) {
  const statusColor =
    wsStatus === 'connected'
      ? 'var(--color-success)'
      : wsStatus === 'connecting'
        ? 'var(--color-warning)'
        : 'var(--color-error)';

  return (
    <header style={styles.header}>
      <div style={styles.left}>
        <span style={styles.logo}>Engram</span>
        <span style={styles.subtitle}>Multi-Agent Support System</span>
      </div>
      <div style={styles.right}>
        <span
          style={{ ...styles.statusDot, backgroundColor: statusColor }}
          title={`WebSocket: ${wsStatus}`}
        />
        <span style={styles.statusText}>{wsStatus}</span>
        {syncStatus && syncStatus !== 'disabled' && (
          <span
            style={{
              ...styles.syncBadge,
              background:
                syncStatus === 'synced' ? 'rgba(76,175,80,0.2)' :
                syncStatus === 'pending' ? 'rgba(255,152,0,0.2)' :
                'rgba(244,67,54,0.2)',
              color:
                syncStatus === 'synced' ? '#4CAF50' :
                syncStatus === 'pending' ? '#FF9800' :
                '#F44336',
            }}
            title={
              syncStatus === 'synced' ? 'Sync: up to date' :
              syncStatus === 'pending' ? `Sync: ${syncPending || 0} pending` :
              'Sync: server offline'
            }
          >
            {syncStatus === 'synced' ? '↑↓' : syncStatus === 'pending' ? `↑${syncPending || ''}` : '⊘'}
          </span>
        )}
        <Link to="/settings" style={styles.gearLink} title="Settings (Ctrl+,)">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
            <path
              d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z"
              stroke="currentColor"
              strokeWidth="1.5"
            />
            <path
              d="M16.17 12.5a1.39 1.39 0 00.28 1.53l.05.05a1.69 1.69 0 01-1.19 2.88 1.69 1.69 0 01-1.19-.49l-.05-.05a1.39 1.39 0 00-1.53-.28 1.39 1.39 0 00-.84 1.27v.14a1.69 1.69 0 11-3.38 0v-.07a1.39 1.39 0 00-.91-1.27 1.39 1.39 0 00-1.53.28l-.05.05a1.69 1.69 0 11-2.39-2.39l.05-.05a1.39 1.39 0 00.28-1.53 1.39 1.39 0 00-1.27-.84h-.14a1.69 1.69 0 110-3.38h.07a1.39 1.39 0 001.27-.91 1.39 1.39 0 00-.28-1.53l-.05-.05a1.69 1.69 0 112.39-2.39l.05.05a1.39 1.39 0 001.53.28h.07a1.39 1.39 0 00.84-1.27v-.14a1.69 1.69 0 113.38 0v.07a1.39 1.39 0 00.84 1.27 1.39 1.39 0 001.53-.28l.05-.05a1.69 1.69 0 112.39 2.39l-.05.05a1.39 1.39 0 00-.28 1.53v.07a1.39 1.39 0 001.27.84h.14a1.69 1.69 0 010 3.38h-.07a1.39 1.39 0 00-1.27.84z"
              stroke="currentColor"
              strokeWidth="1.5"
            />
          </svg>
        </Link>
      </div>
    </header>
  );
}

const styles: Record<string, React.CSSProperties> = {
  header: {
    height: 'var(--header-height)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 20px',
    background: 'var(--brand-primary)',
    color: 'var(--text-on-dark)',
    flexShrink: 0,
  },
  left: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  logo: {
    fontWeight: 700,
    fontSize: '18px',
    letterSpacing: '2px',
  },
  title: {
    fontWeight: 600,
    fontSize: '16px',
  },
  subtitle: {
    fontSize: '12px',
    opacity: 0.7,
  },
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  statusDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
  },
  statusText: {
    fontSize: '12px',
    opacity: 0.8,
    textTransform: 'capitalize' as const,
  },
  syncBadge: {
    fontSize: '11px',
    fontWeight: 600,
    padding: '2px 8px',
    borderRadius: '10px',
    letterSpacing: '0.5px',
  },
  gearLink: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '32px',
    height: '32px',
    borderRadius: 'var(--radius-sm)',
    color: 'rgba(255,255,255,0.8)',
    textDecoration: 'none',
    transition: 'background 0.15s, color 0.15s',
  },
};
