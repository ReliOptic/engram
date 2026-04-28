import { useEffect, useRef, useState } from 'react';
import type { AgentMessage, AgentRole } from '../types';

interface ChatTimelineProps {
  messages: AgentMessage[];
  isProcessing?: boolean;
  terminatedReason?: string | null;
  sessionId?: string | null;
  onSourceBadgeClick?: (chunkId: string) => void;
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


const SOURCE_ID_RE = /source_id_[a-z0-9_]+/g;

/** Extract source_id tokens from text, returning cleaned text and badge IDs. */
export function parseSourceIds(text: string): { text: string; badges: string[] } {
  const badges: string[] = [];
  const cleaned = text.replace(SOURCE_ID_RE, (match) => {
    badges.push(match);
    return '';
  }).replace(/  +/g, ' ').trim();
  return { text: cleaned, badges };
}

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

// ── Session footer (summary + feedback merged) ───────────────────────────────

function SessionFooter({ messages, terminatedReason, sessionId }: {
  messages: AgentMessage[];
  terminatedReason: string;
  sessionId: string;
}) {
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const agentMessages = messages.filter((m) => m.agent !== 'user');
  const counterCount = agentMessages.filter((m) => m.contributionType === 'COUNTER').length;
  const passCount = agentMessages.filter((m) => m.contributionType === 'PASS').length;
  const consensusCount = agentMessages.filter((m) =>
    m.contributionType === 'NEW_EVIDENCE' ||
    m.contributionType === 'REVISE'
  ).length;

  const lastAgentMessages = agentMessages.slice(-3);
  const hasUnresolvedCounter = lastAgentMessages.some((m) => m.contributionType === 'COUNTER');

  const submit = async (helpful: boolean) => {
    setLoading(true);
    try {
      await fetch(`/api/sessions/${sessionId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ helpful }),
      });
      setSubmitted(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.sessionFooter}>
      <div style={styles.footerStats}>
        <span style={styles.summaryText}>
          합의 {consensusCount}개 · 이견 {counterCount}개 · 패스 {passCount}개
        </span>
        {hasUnresolvedCounter && (
          <span style={styles.unresolvedBadge}>⚠️ 미해소 이견 있음</span>
        )}
        {terminatedReason === 'all_pass' && (
          <span style={styles.resolvedBadge}>합의 완료</span>
        )}
      </div>
      <div style={styles.footerFeedback}>
        {submitted ? (
          <span style={styles.feedbackThanks}>피드백 감사합니다</span>
        ) : (
          <>
            <span style={styles.feedbackQuestion}>선례 검색이 도움이 됐나요?</span>
            <button style={{ ...styles.feedbackBtn, ...styles.feedbackBtnYes }} onClick={() => submit(true)} disabled={loading}>예</button>
            <button style={{ ...styles.feedbackBtn, ...styles.feedbackBtnNo }} onClick={() => submit(false)} disabled={loading}>아니오</button>
          </>
        )}
      </div>
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────────────────────

export function ChatTimeline({ messages, isProcessing, terminatedReason, sessionId, onSourceBadgeClick }: ChatTimelineProps) {
  const timelineRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (timelineRef.current) {
      timelineRef.current.scrollTop = timelineRef.current.scrollHeight;
    }
  }, [messages, isProcessing]);

  if (messages.length === 0) {
    return <EmptyState />;
  }

  const showSummary = !isProcessing && terminatedReason != null && messages.length >= 1;
  const showFeedback = !isProcessing && !!sessionId && terminatedReason != null;

  return (
    <div ref={timelineRef} style={styles.timeline}>
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} onSourceBadgeClick={onSourceBadgeClick} />
      ))}
      {isProcessing && <ThinkingIndicator />}
      {(showSummary || showFeedback) && (
        <SessionFooter
          messages={messages}
          terminatedReason={terminatedReason ?? ''}
          sessionId={sessionId ?? ''}
        />
      )}
    </div>
  );
}

// ── Message bubble ───────────────────────────────────────────────────────────

function MessageBubble({ message, onSourceBadgeClick }: { message: AgentMessage; onSourceBadgeClick?: (chunkId: string) => void }) {
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

  const isCounter = message.contributionType === 'COUNTER';
  const isRevise = message.contributionType === 'REVISE';

  const bubbleStyle: React.CSSProperties = {
    ...styles.bubble,
    ...(isCounter ? { borderLeft: '3px solid #FB923C', paddingLeft: '13px' } : {}),
    ...(isRevise ? { borderLeft: '2px solid #FDE047', paddingLeft: '14px' } : {}),
  };

  return (
    <div style={bubbleStyle}>
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
        {message.contributionType && ctColors && message.contributionType !== 'COUNTER' && (
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
        {isCounter && (
          <span style={styles.counterBadge}>반박</span>
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
      {(() => {
        const { text: cleanedText, badges } = parseSourceIds(message.content);
        return (
          <>
            <div style={styles.content}>{renderContent(cleanedText)}</div>
            {badges.length > 0 && (
              <div style={styles.badgeRow}>
                {badges.map((badge) => (
                  <button
                    key={badge}
                    style={styles.sourceBadge}
                    onClick={() => onSourceBadgeClick?.(badge)}
                    title={badge}
                  >
                    {badge.replace(/^source_id_/, '')}
                  </button>
                ))}
              </div>
            )}
          </>
        );
      })()}
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
  counterBadge: {
    fontSize: '10px',
    fontWeight: 700,
    padding: '2px 7px',
    borderRadius: 'var(--radius-pill)',
    background: '#FED7AA',
    color: '#C2410C',
    letterSpacing: '0.2px',
  },
  summaryBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '8px 14px',
    marginTop: '4px',
    background: 'var(--bg-secondary)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-light)',
    flexWrap: 'wrap' as const,
  },
  summaryText: {
    fontSize: '12px',
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  unresolvedBadge: {
    fontSize: '11px',
    fontWeight: 600,
    padding: '2px 8px',
    borderRadius: 'var(--radius-pill)',
    background: '#FEF3C7',
    color: '#D97706',
  },
  resolvedBadge: {
    fontSize: '11px',
    fontWeight: 600,
    padding: '2px 8px',
    borderRadius: 'var(--radius-pill)',
    background: '#DCFCE7',
    color: '#15803D',
  },
  sessionFooter: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px',
    padding: '10px 14px',
    marginTop: '4px',
    background: 'var(--bg-secondary)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-light)',
    animation: 'fadeIn 0.2s ease',
  },
  footerStats: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    flexWrap: 'wrap' as const,
  },
  footerFeedback: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    paddingTop: '8px',
    borderTop: '1px solid var(--border-light)',
    flexWrap: 'wrap' as const,
  },
  feedbackBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 14px',
    marginTop: '4px',
    background: 'var(--bg-secondary)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-light)',
    flexWrap: 'wrap' as const,
    animation: 'fadeIn 0.2s ease',
  },
  feedbackQuestion: {
    fontSize: '13px',
    color: 'var(--text-primary)',
    fontWeight: 500,
    flex: 1,
  },
  feedbackThanks: {
    fontSize: '13px',
    color: 'var(--text-muted)',
    fontStyle: 'italic',
  },
  feedbackBtn: {
    padding: '4px 14px',
    borderRadius: 'var(--radius-pill)',
    fontSize: '12px',
    fontWeight: 600,
    cursor: 'pointer',
    border: '1px solid transparent',
  },
  feedbackBtnYes: {
    background: '#DCFCE7',
    color: '#15803D',
    borderColor: '#86EFAC',
  },
  feedbackBtnNo: {
    background: 'var(--bg-primary)',
    color: 'var(--text-secondary)',
    borderColor: 'var(--border-light)',
  },
};
