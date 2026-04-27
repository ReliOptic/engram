import type { AgentInfo, AgentStatus } from '../types';

const AGENTS: AgentInfo[] = [
  {
    role: 'analyzer',
    displayName: 'Analyzer',
    description: 'Root cause analysis',
    color: 'var(--agent-analyzer)',
    status: 'idle',
  },
  {
    role: 'finder',
    displayName: 'Finder',
    description: 'Knowledge search',
    color: 'var(--agent-finder)',
    status: 'idle',
  },
  {
    role: 'reviewer',
    displayName: 'Reviewer',
    description: 'Procedure validation',
    color: 'var(--agent-reviewer)',
    status: 'idle',
  },
];

interface AgentPanelProps {
  agentStatuses?: Record<string, AgentStatus>;
}

export function AgentPanel({ agentStatuses }: AgentPanelProps) {
  return (
    <div style={styles.panel}>
      <h3 style={styles.heading}>Agents</h3>
      <div style={styles.cards}>
        {AGENTS.map((agent) => {
          const status = agentStatuses?.[agent.role] ?? agent.status;
          const isActive = status === 'thinking' || status === 'processing';
          const isDone = status === 'done';

          const cardStyle: React.CSSProperties = {
            ...styles.card,
            ...(isActive
              ? {
                  borderLeft: `3px solid ${agent.color}`,
                  paddingLeft: '9px', // compensate for thicker border
                  background: 'var(--bg-primary)',
                }
              : isDone
              ? { background: '#F0FDF4', borderColor: '#BBF7D0' }
              : {}),
          };

          return (
            <div key={agent.role} style={cardStyle}>
              <div style={styles.cardHeader}>
                <div
                  style={{
                    ...styles.avatar,
                    backgroundColor: agent.color,
                  }}
                >
                  {agent.displayName[0]}
                </div>
                <div style={styles.cardInfo}>
                  <span style={styles.name}>{agent.displayName}</span>
                  <span style={styles.desc}>{agent.description}</span>
                </div>
              </div>
              <StatusBadge status={status} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: AgentStatus }) {
  const config: Record<AgentStatus, { bg: string; text: string; label: string }> = {
    idle:       { bg: 'var(--bg-secondary)', text: 'var(--text-muted)',    label: 'Idle' },
    thinking:   { bg: '#EEF2FF',            text: 'var(--brand-primary)', label: 'Thinking' },
    done:       { bg: '#DCFCE7',            text: '#15803D',              label: 'Done' },
    waiting:    { bg: '#FFF7ED',            text: '#D97706',              label: 'Waiting' },
    processing: { bg: '#EEF2FF',            text: 'var(--brand-primary)', label: 'Processing' },
  };
  const c = config[status];
  const isAnimated = status === 'thinking' || status === 'processing';

  return (
    <span
      style={{
        fontSize: '11px',
        fontWeight: 500,
        padding: '2px 8px',
        borderRadius: 'var(--radius-pill)',
        background: c.bg,
        color: c.text,
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
      }}
    >
      {isAnimated ? (
        <ThinkingDots color={c.text} />
      ) : (
        c.label
      )}
    </span>
  );
}

function ThinkingDots({ color }: { color: string }) {
  return (
    <span style={{ display: 'inline-flex', gap: '3px', alignItems: 'center' }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            display: 'inline-block',
            width: '5px',
            height: '5px',
            borderRadius: '50%',
            background: color,
            animation: 'dotPulse 1.2s ease-in-out infinite',
            animationDelay: `${i * 0.18}s`,
          }}
        />
      ))}
    </span>
  );
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
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
  cards: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  card: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 12px',
    background: 'var(--bg-primary)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-light)',
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
    transition: 'background 0.2s, border-color 0.2s, box-shadow 0.2s',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  avatar: {
    width: '32px',
    height: '32px',
    borderRadius: 'var(--radius-md)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'white',
    fontWeight: 600,
    fontSize: '14px',
  },
  cardInfo: {
    display: 'flex',
    flexDirection: 'column',
  },
  name: {
    fontWeight: 600,
    fontSize: '13px',
    color: 'var(--text-primary)',
  },
  desc: {
    fontSize: '11px',
    color: 'var(--text-muted)',
  },
};
