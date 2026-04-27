import { useEffect, useRef } from 'react';
import type { AgentMessage, AgentRole } from '../types';

interface ChatTimelineProps {
  messages: AgentMessage[];
  isProcessing?: boolean;
}

const AGENT_COLORS: Record<AgentRole, string> = {
  analyzer: 'var(--agent-analyzer)',
  finder: 'var(--agent-finder)',
  reviewer: 'var(--agent-reviewer)',
  user: 'var(--brand-primary)',
};

const AGENT_NAMES: Record<AgentRole, string> = {
  analyzer: 'Analyzer',
  finder: 'Finder',
  reviewer: 'Reviewer',
  user: 'You',
};

const CONTRIBUTION_COLORS: Record<
  string,
  { bg: string; text: string }
> = {
  NEW_EVIDENCE:    { bg: '#DBEAFE', text: '#1D4ED8' },
  COUNTER:         { bg: '#FFEDD5', text: '#C2410C' },
  ASK_STAKEHOLDER: { bg: '#EDE9FE', text: '#6D28D9' },
  REVISE:          { bg: '#FEF9C3', text: '#A16207' },
  PASS:            { bg: 'var(--bg-secondary)', text: 'var(--text-secondary)' },
};

/** Parse **bold** markers into React nodes with <strong>. */
function parseBold(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

/** Highlight @mentions AND parse **bold** inside each segment. */
function renderContent(text: string): React.ReactNode {
  const mentionParts = text.split(/(@\w+)/g);
  return mentionParts.map((segment, i) =>
    segment.startsWith('@') ? (
      <span key={i} style={styles.mention}>
        {segment}
      </span>
    ) : (
      <span key={i}>{parseBold(segment)}</span>
    ),
  );
}

// ── Agent avatar used in empty state and thinking indicator ──────────────────

function AgentAvatar({
  role,
  size = 36,
  pulsing = false,
  pulseDelay = '0s',
}: {
  role: AgentRole;
  size?: number;
  pulsing?: boolean;
  pulseDelay?: string;
}) {
  const color = AGENT_COLORS[role];
  const initial = AGENT_NAMES[role][0];
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: 'var(--radius-md)',
        backgroundColor: color,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'white',
        fontSize: size * 0.42,
        fontWeight: 700,
        flexShrink: 0,
        animation: pulsing ? `pulse 1.4s ease-in-out infinite` : 'none',
        animationDelay: pulseDelay,
        transition: 'opacity 0.15s',
      }}
    >
      {initial}
    </div>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div style={styles.empty}>
      <div style={styles.emptyAvatars}>
        <AgentAvatar role="analyzer" size={44} />
        <AgentAvatar role="finder" size={44} />
        <AgentAvatar role="reviewer" size={44} />
      </div>
      <p style={styles.emptyTitle}>3 Agents Ready</p>
      <p style={styles.emptyText}>
        Describe your issue below — Analyzer, Finder, and Reviewer will
        collaborate to resolve it.
      </p>
    </div>
  );
}

// ── Thinking indicator ───────────────────────────────────────────────────────

function ThinkingIndicator() {
  const agents: AgentRole[] = ['analyzer', 'finder', 'reviewer'];
  return (
    <div style={styles.thinkingRow}>
      {agents.map((role, idx) => (
        <AgentAvatar
          key={role}
          role={role}
          size={24}
          pulsing
          pulseDelay={`${idx * 0.22}s`}
        />
      ))}
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────────────────────

export function ChatTimeline({ messages, isProcessing }: ChatTimelineProps) {
  const timelineRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (timelineRef.current) {
      timelineRef.current.scrollTop = timelineRef.current.scrollHeight;
    }
  }, [messages, isProcessing]);

  if (messages.length === 0) {
    return <EmptyState />;
  }

  return (
    <div ref={timelineRef} style={styles.timeline}>
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isProcessing && <ThinkingIndicator />}
    </div>
  );
}

// ── Message bubble ───────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: AgentMessage }) {
  const isUser = message.agent === 'user';
  const agentColor = AGENT_COLORS[message.agent] ?? 'var(--brand-primary)';
  const agentName = AGENT_NAMES[message.agent] ?? message.agent;

  if (isUser) {
    return (
      <div style={styles.userBubbleWrapper}>
        <div style={styles.userBubble}>
          <div style={styles.userHeader}>
            <span style={styles.userLabel}>You</span>
            <span style={styles.time}>
              {new Date(message.timestamp).toLocaleTimeString()}
            </span>
          </div>
          <div style={styles.userContent}>{renderContent(message.content)}</div>
          {message.silo && (
            <div style={styles.siloBadge}>
              {message.silo.account} / {message.silo.tool} / {message.silo.component}
            </div>
          )}
        </div>
      </div>
    );
  }

  const ctColors = message.contributionType
    ? (CONTRIBUTION_COLORS[message.contributionType] ?? CONTRIBUTION_COLORS['PASS'])
    : null;

  return (
    <div style={styles.bubble}>
      <div style={styles.bubbleHeader}>
        <span
          style={{
            ...styles.agentBadge,
            backgroundColor: agentColor,
          }}
        >
          {agentName[0]}
        </span>
        <span style={styles.agentName}>{agentName}</span>
        {message.contributionType && ctColors && (
          <span
            style={{
              ...styles.tag,
              background: ctColors.bg,
              color: ctColors.text,
            }}
          >
            {message.contributionType}
          </span>
        )}
        {message.addressedTo && (
          <span style={styles.addressedTo}>
            → @{message.addressedTo.replace(/^@/, '')}
          </span>
        )}
        <span style={styles.time}>
          {new Date(message.timestamp).toLocaleTimeString()}
        </span>
      </div>
      <div style={styles.content}>{renderContent(message.content)}</div>
    </div>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  timeline: {
    flex: 1,
    overflowY: 'auto',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  // Empty state
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '14px',
    color: 'var(--text-muted)',
    padding: '32px',
  },
  emptyAvatars: {
    display: 'flex',
    gap: '12px',
    marginBottom: '4px',
  },
  emptyTitle: {
    fontSize: '15px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    letterSpacing: '0.2px',
  },
  emptyText: {
    fontSize: '13px',
    maxWidth: '320px',
    textAlign: 'center',
    lineHeight: '1.6',
  },
  // Thinking indicator
  thinkingRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 4px',
  },
  // Agent bubbles
  bubble: {
    padding: '12px 16px',
    background: 'var(--bg-primary)',
    borderRadius: 'var(--radius-lg)',
    border: '1px solid var(--border-light)',
    alignSelf: 'flex-start',
    maxWidth: '85%',
    animation: 'fadeIn 0.2s ease',
  },
  bubbleHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '8px',
  },
  agentBadge: {
    width: '22px',
    height: '22px',
    borderRadius: 'var(--radius-sm)',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'white',
    fontSize: '11px',
    fontWeight: 700,
    flexShrink: 0,
  },
  agentName: {
    fontWeight: 600,
    fontSize: '13px',
    color: 'var(--text-primary)',
  },
  tag: {
    fontSize: '10px',
    fontWeight: 600,
    padding: '2px 7px',
    borderRadius: 'var(--radius-pill)',
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
  },
  addressedTo: {
    fontSize: '11px',
    color: 'var(--brand-link)',
    fontWeight: 500,
  },
  time: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    marginLeft: 'auto',
  },
  content: {
    fontSize: '13px',
    lineHeight: '1.6',
    color: 'var(--text-primary)',
    whiteSpace: 'pre-wrap',
  },
  mention: {
    color: 'var(--brand-link)',
    fontWeight: 600,
  },
  // User bubble
  userBubbleWrapper: {
    display: 'flex',
    justifyContent: 'flex-end',
    animation: 'fadeIn 0.2s ease',
  },
  userBubble: {
    padding: '12px 16px',
    background: 'var(--brand-primary)',
    borderRadius: 'var(--radius-lg)',
    maxWidth: '75%',
  },
  userHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '6px',
  },
  userLabel: {
    fontWeight: 600,
    fontSize: '13px',
    color: 'rgba(255,255,255,0.9)',
  },
  userContent: {
    fontSize: '13px',
    lineHeight: '1.6',
    color: '#FFFFFF',
    whiteSpace: 'pre-wrap',
  },
  siloBadge: {
    marginTop: '8px',
    padding: '2px 8px',
    borderRadius: 'var(--radius-pill)',
    background: 'rgba(255,255,255,0.15)',
    color: 'rgba(255,255,255,0.8)',
    fontSize: '10px',
    fontWeight: 500,
    display: 'inline-block',
  },
};
