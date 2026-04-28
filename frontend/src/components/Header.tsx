import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';
type SyncStatus = 'disabled' | 'synced' | 'pending' | 'offline';
type DreamingStatus = 'ok' | 'never_run' | 'failed';

interface KnowledgeHealth {
  total_cases: number;
  total_chunks: number;
  last_dreaming_run: string | null;
  dreaming_status: DreamingStatus;
  weekly_files_processed: number;
  feedback_positive_rate: number | null;
}

interface HeaderProps {
  wsStatus: ConnectionStatus;
  syncStatus?: SyncStatus;
  syncPending?: number;
  onThemeToggle?: () => void;
}

type ActiveTab = 'chat' | 'knowledge' | 'settings';

function Icon({ d, size = 18 }: { d: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={d} />
    </svg>
  );
}

const MOON_PATH = 'M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z';
const SETTINGS_PATHS = [
  'M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9z',
];

export function Header({ wsStatus, syncStatus: _syncStatus, syncPending: _syncPending, onThemeToggle }: HeaderProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>('chat');
  const [knowledgeHealth, setKnowledgeHealth] = useState<KnowledgeHealth | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchHealth = () => {
      fetch('/api/knowledge/health')
        .then((r) => r.json())
        .then((data: KnowledgeHealth) => setKnowledgeHealth(data))
        .catch(() => {});
    };
    fetchHealth();
    const interval = setInterval(fetchHealth, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const healthDotColor = (() => {
    if (!knowledgeHealth) return 'var(--text-faint)';
    if (knowledgeHealth.dreaming_status === 'failed') return 'var(--color-error)';
    if (knowledgeHealth.total_cases === 0 || knowledgeHealth.dreaming_status === 'never_run')
      return 'var(--color-warning)';
    return 'var(--color-success)';
  })();

  const healthTooltip = (() => {
    if (!knowledgeHealth) return 'Knowledge base: loading';
    const lastRun = knowledgeHealth.last_dreaming_run
      ? new Date(knowledgeHealth.last_dreaming_run).toLocaleDateString('ko-KR')
      : 'never';
    return `Knowledge: ${knowledgeHealth.total_cases} cases · last refined: ${lastRun}`;
  })();

  const wsBadgeStyle = (() => {
    if (wsStatus === 'connected')
      return { bg: 'var(--color-success-soft)', text: 'var(--color-success-text)', dot: 'var(--color-success)' };
    if (wsStatus === 'connecting')
      return { bg: 'var(--color-warning-soft)', text: 'var(--color-warning-text)', dot: 'var(--color-warning)' };
    return { bg: 'var(--color-error-soft)', text: 'var(--color-error-text)', dot: 'var(--color-error)' };
  })();

  const handleTabClick = (tab: ActiveTab) => {
    setActiveTab(tab);
    if (tab === 'settings') {
      navigate('/settings');
    }
  };

  return (
    <header style={styles.header}>
      {/* Left: monogram + title */}
      <div style={styles.left}>
        <div style={styles.monogram}>EG</div>
        <div style={styles.titleBlock}>
          <span style={styles.titlePrimary}>ENGRAM</span>
          <span style={styles.titleSub}>FIELD AI · 3 AGENTS</span>
        </div>
      </div>

      {/* Center: tab switcher */}
      <div style={styles.tabPill}>
        {(['chat', 'knowledge', 'settings'] as ActiveTab[]).map((tab) => (
          <button
            key={tab}
            style={{
              ...styles.tabBtn,
              ...(activeTab === tab ? styles.tabBtnActive : {}),
            }}
            onClick={() => handleTabClick(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Right: WS badge + icon buttons */}
      <div style={styles.right}>
        {/* Knowledge health indicator */}
        <span style={styles.healthIndicator} title={healthTooltip}>
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              backgroundColor: healthDotColor,
              display: 'inline-block',
              flexShrink: 0,
            }}
          />
          <span style={styles.healthLabel}>知</span>
        </span>

        {/* WS connection badge */}
        <span
          style={{
            ...styles.wsBadge,
            background: wsBadgeStyle.bg,
            color: wsBadgeStyle.text,
          }}
          title={`WebSocket: ${wsStatus}`}
        >
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              backgroundColor: wsBadgeStyle.dot,
              display: 'inline-block',
              flexShrink: 0,
            }}
          />
          {wsStatus}
        </span>

        {/* Moon / theme toggle */}
        <button
          style={styles.iconBtn}
          onClick={onThemeToggle}
          title="Toggle theme"
          aria-label="Toggle dark mode"
        >
          <Icon d={MOON_PATH} size={16} />
        </button>

        {/* Settings icon */}
        <Link to="/settings" style={styles.iconBtnLink} title="Settings (Ctrl+,)" aria-label="Settings">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="3" />
            <path d={SETTINGS_PATHS[0]} />
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
    padding: '0 16px',
    background: 'var(--surface-panel)',
    flexShrink: 0,
    borderBottom: '1px solid var(--border-hairline)',
  },
  left: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    flex: '0 0 auto',
  },
  monogram: {
    width: '28px',
    height: '28px',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--brand-primary)',
    color: '#FFFFFF',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '11px',
    fontWeight: 700,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '0.5px',
    flexShrink: 0,
  },
  titleBlock: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1px',
  },
  titlePrimary: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    letterSpacing: '1.5px',
    lineHeight: 1,
    fontFamily: 'var(--font-sans)',
  },
  titleSub: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    letterSpacing: '1px',
    lineHeight: 1,
    fontFamily: 'var(--font-mono)',
  },
  tabPill: {
    display: 'flex',
    alignItems: 'center',
    background: 'var(--surface-sunken)',
    borderRadius: 'var(--radius-pill)',
    padding: '3px',
    gap: '2px',
    border: '1px solid var(--border-hairline)',
  },
  tabBtn: {
    padding: '4px 14px',
    borderRadius: 'var(--radius-pill)',
    border: 'none',
    background: 'transparent',
    color: 'var(--text-muted)',
    fontSize: '12px',
    fontWeight: 500,
    fontFamily: 'var(--font-sans)',
    cursor: 'pointer',
    transition: 'background 0.15s, color 0.15s',
    whiteSpace: 'nowrap' as const,
  },
  tabBtnActive: {
    background: 'var(--surface-panel)',
    color: 'var(--text-primary)',
    fontWeight: 600,
    boxShadow: 'var(--shadow-xs)',
  },
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flex: '0 0 auto',
  },
  healthIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    cursor: 'default',
  },
  healthLabel: {
    fontSize: '10px',
    color: 'var(--text-faint)',
  },
  wsBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '3px 8px',
    borderRadius: 'var(--radius-pill)',
    fontSize: '11px',
    fontWeight: 500,
    textTransform: 'capitalize' as const,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '0.2px',
  },
  iconBtn: {
    width: '30px',
    height: '30px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-hairline)',
    background: 'transparent',
    color: 'var(--text-secondary)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    flexShrink: 0,
    transition: 'background 0.15s, color 0.15s',
  },
  iconBtnLink: {
    width: '30px',
    height: '30px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-hairline)',
    background: 'transparent',
    color: 'var(--text-secondary)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    textDecoration: 'none',
    transition: 'background 0.15s, color 0.15s',
  },
};
