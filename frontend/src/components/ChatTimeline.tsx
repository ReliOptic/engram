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
  const cleaned = text
    .replace(SOURCE_ID_RE, (match) => {
      badges.push(match);
      return '';
    })
    .replace(/  +/g, ' ')
    .trim();
  return { text: cleaned, badges };
}

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

// ── AgentGlyph: inline icon per agent role ───────────────────────────────────

function AgentGlyph({ role, size = 28 }: { role: AgentRole; size?: number }) {
  const isAnalyzer = role === 'analyzer';
  const isFinder = role === 'finder';
  const isReviewer = role === 'reviewer';

  const bgColor = isAnalyzer
    ? '#2563EB'
    : isFinder
      ? '#0EA5A5'
      : isReviewer
        ? '#6E5EFF'
        : 'var(--brand-primary)';

  const borderRadius = isFinder ? '50%' : isReviewer ? '6px' : '8px';

  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius,
        backgroundColor: bgColor,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}
    >
      {isAnalyzer && (
        <svg width={size * 0.54} height={size * 0.54} viewBox="0 0 16 16" fill="none">
          <path
            d="M2 10 Q5 4 8 8 Q11 12 14 6"
            stroke="white"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      )}
      {isFinder && (
        <svg width={size * 0.54} height={size * 0.54} viewBox="0 0 16 16" fill="none">
          <circle cx="6.5" cy="6.5" r="4" stroke="white" strokeWidth="1.7" />
          <line x1="9.5" y1="9.5" x2="13" y2="13" stroke="white" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      )}
      {isReviewer && (
        <svg width={size * 0.54} height={size * 0.54} viewBox="0 0 16 16" fill="none">
          <polyline
            points="3,8 6.5,12 13,4"
            stroke="white"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      )}
      {!isAnalyzer && !isFinder && !isReviewer && (
        <span style={{ color: 'white', fontSize: size * 0.42, fontWeight: 700 }}>
          {AGENT_NAMES[role]?.[0] ?? '?'}
        </span>
      )}
    </div>
  );
}

// ── ContributionPill ─────────────────────────────────────────────────────────

const CT_PILL_STYLES: Record<string, { bg: string; fg: string; dot?: boolean }> = {
  NEW_EVIDENCE:    { bg: 'var(--ct-evidence-bg)',  fg: 'var(--ct-evidence-fg)' },
  COUNTER:         { bg: 'var(--ct-counter-bg)',   fg: 'var(--ct-counter-fg)',  dot: true },
  ASK_STAKEHOLDER: { bg: 'var(--ct-ask-bg)',        fg: 'var(--ct-ask-fg)' },
  REVISE:          { bg: 'var(--ct-revise-bg)',     fg: 'var(--ct-revise-fg)' },
  PASS:            { bg: 'var(--ct-pass-bg)',       fg: 'var(--ct-pass-fg)' },
};

const CT_LABELS: Record<string, string> = {
  NEW_EVIDENCE:    'Evidence',
  COUNTER:         'Counter',
  ASK_STAKEHOLDER: 'Ask',
  REVISE:          'Revise',
  PASS:            'Pass',
};

function ContributionPill({ type }: { type: string }) {
  const pill = CT_PILL_STYLES[type] ?? CT_PILL_STYLES['PASS'];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '2px 8px',
        borderRadius: 'var(--radius-pill)',
        background: pill.bg,
        color: pill.fg,
        fontSize: '10px',
        fontWeight: 600,
        letterSpacing: '0.3px',
        textTransform: 'uppercase' as const,
        lineHeight: 1.6,
      }}
    >
      {pill.dot && (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            backgroundColor: 'var(--ct-counter-fg)',
            flexShrink: 0,
          }}
        />
      )}
      {CT_LABELS[type] ?? type}
    </span>
  );
}

// ── EmptyState ───────────────────────────────────────────────────────────────

const SEED_PROMPTS = [
  'Diagnose a recurring failure',
  'Find a similar past case',
  'Validate a fix procedure',
];

function EmptyState() {
  return (
    <div style={styles.empty}>
      <div style={styles.emptyGlyphs}>
        <AgentGlyph role="analyzer" size={48} />
        <AgentGlyph role="finder" size={48} />
        <AgentGlyph role="reviewer" size={48} />
      </div>
      <h2 style={styles.emptyTitle}>Three agents are ready.</h2>
      <p style={styles.emptyText}>
        Describe your issue and Analyzer, Finder, and Reviewer will collaborate to diagnose and resolve it.
      </p>
      <div style={styles.seedRow}>
        {SEED_PROMPTS.map((prompt) => (
          <button key={prompt} style={styles.seedBtn}>
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
              <path
                d="M8 1L9.5 5.5H14.5L10.5 8.5L12 13L8 10L4 13L5.5 8.5L1.5 5.5H6.5L8 1Z"
                fill="var(--brand-primary)"
              />
            </svg>
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── ProcessingRow ────────────────────────────────────────────────────────────

function ProcessingRow() {
  return (
    <div style={styles.processingRow}>
      <AgentGlyph role="analyzer" size={20} />
      <AgentGlyph role="finder" size={20} />
      <AgentGlyph role="reviewer" size={20} />
      <span style={styles.processingText}>Agents collaborating</span>
      <span style={styles.dotBlink}>
        <span>.</span>
        <span style={{ animationDelay: '0.2s' }}>.</span>
        <span style={{ animationDelay: '0.4s' }}>.</span>
      </span>
    </div>
  );
}

// ── SessionFooter (CaseCompletion style) ─────────────────────────────────────

function SessionFooter({
  messages,
  terminatedReason,
  sessionId,
}: {
  messages: AgentMessage[];
  terminatedReason: string;
  sessionId: string;
}) {
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const agentMessages = messages.filter((m) => m.agent !== 'user');
  const counterCount = agentMessages.filter((m) => m.contributionType === 'COUNTER').length;
  const passCount = agentMessages.filter((m) => m.contributionType === 'PASS').length;
  const consensusCount = agentMessages.filter(
    (m) => m.contributionType === 'NEW_EVIDENCE' || m.contributionType === 'REVISE',
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
      {/* Header row */}
      <div style={styles.footerHeaderRow}>
        <div style={styles.footerSparkleIcon}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path
              d="M8 1L9.5 5.5H14.5L10.5 8.5L12 13L8 10L4 13L5.5 8.5L1.5 5.5H6.5L8 1Z"
              fill="white"
            />
          </svg>
        </div>
        <span style={styles.footerTitle}>Recommended sequence</span>
        {terminatedReason === 'all_pass' && (
          <span style={styles.resolvedBadge}>Consensus reached</span>
        )}
        {hasUnresolvedCounter && (
          <span style={styles.unresolvedBadge}>Unresolved counter</span>
        )}
      </div>

      {/* Stats row */}
      <div style={styles.footerStats}>
        <span style={styles.statPill}>
          <span style={styles.statLabel}>Evidence</span>
          <span style={styles.statValue}>{consensusCount}</span>
        </span>
        <span style={styles.statPill}>
          <span style={styles.statLabel}>Counter</span>
          <span style={styles.statValue}>{counterCount}</span>
        </span>
        <span style={styles.statPill}>
          <span style={styles.statLabel}>Pass</span>
          <span style={styles.statValue}>{passCount}</span>
        </span>
      </div>

      {/* Feedback row */}
      <div style={styles.footerFeedback}>
        {submitted ? (
          <span style={styles.feedbackThanks}>Thank you for your feedback</span>
        ) : (
          <>
            <span style={styles.feedbackQuestion}>Was this session helpful?</span>
            <button
              style={{ ...styles.feedbackBtn, ...styles.feedbackBtnYes }}
              onClick={() => submit(true)}
              disabled={loading}
            >
              Yes, resolved
            </button>
            <button
              style={{ ...styles.feedbackBtn, ...styles.feedbackBtnNo }}
              onClick={() => submit(false)}
              disabled={loading}
            >
              Not quite
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ── UserBubble ───────────────────────────────────────────────────────────────

function UserBubble({ message }: { message: AgentMessage }) {
  return (
    <div style={styles.userBubbleWrapper}>
      <div style={styles.userBubble}>
        <div style={styles.userHeader}>
          <span style={styles.userLabel}>You</span>
          <span style={styles.userTime}>
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

// ── PassRow (minimized inline) ───────────────────────────────────────────────

function PassRow({ message }: { message: AgentMessage }) {
  const role = message.agent as AgentRole;
  const agentName = AGENT_NAMES[role] ?? message.agent;
  return (
    <div style={styles.passRow}>
      <AgentGlyph role={role} size={20} />
      <span style={styles.passAgentName}>{agentName}</span>
      <ContributionPill type="PASS" />
      <span style={styles.passContent}>{message.content}</span>
    </div>
  );
}

// ── AgentBubble ──────────────────────────────────────────────────────────────

function AgentBubble({
  message,
  onSourceBadgeClick,
}: {
  message: AgentMessage;
  onSourceBadgeClick?: (chunkId: string) => void;
}) {
  const role = message.agent as AgentRole;
  const agentColor = AGENT_COLORS[role] ?? 'var(--brand-primary)';
  const agentName = AGENT_NAMES[role] ?? message.agent;
  const ct = message.contributionType ?? '';

  const isCounter = ct === 'COUNTER';
  const isRevise = ct === 'REVISE';
  const isAsk = ct === 'ASK_STAKEHOLDER';

  const leftBorder: React.CSSProperties = isCounter
    ? { borderLeft: '3px solid var(--ct-counter-edge)', paddingLeft: '13px' }
    : isRevise
      ? { borderLeft: '2px solid var(--ct-revise-edge)', paddingLeft: '14px' }
      : isAsk
        ? { borderLeft: '2px solid var(--ct-ask-edge)', paddingLeft: '14px' }
        : {};

  const bubbleStyle: React.CSSProperties = {
    ...styles.bubble,
    ...leftBorder,
  };

  const { text: cleanedText, badges } = parseSourceIds(message.content);

  return (
    <div style={bubbleStyle}>
      <div style={styles.bubbleHeader}>
        <AgentGlyph role={role} size={28} />
        <span style={{ ...styles.agentName, color: agentColor }}>{agentName}</span>
        {ct && <ContributionPill type={ct} />}
        {message.addressedTo && (
          <span style={styles.addressedTo}>
            → @{message.addressedTo.replace(/^@/, '')}
          </span>
        )}
        <span style={styles.time}>
          {new Date(message.timestamp).toLocaleTimeString()}
        </span>
      </div>
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
    </div>
  );
}

// ── MessageBubble dispatcher ─────────────────────────────────────────────────

function MessageBubble({
  message,
  onSourceBadgeClick,
}: {
  message: AgentMessage;
  onSourceBadgeClick?: (chunkId: string) => void;
}) {
  if (message.agent === 'user') {
    return <UserBubble message={message} />;
  }
  if (message.contributionType === 'PASS') {
    return <PassRow message={message} />;
  }
  return <AgentBubble message={message} onSourceBadgeClick={onSourceBadgeClick} />;
}

// ── Main export ──────────────────────────────────────────────────────────────

export function ChatTimeline({
  messages,
  isProcessing,
  terminatedReason,
  sessionId,
  onSourceBadgeClick,
}: ChatTimelineProps) {
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
      {isProcessing && <ProcessingRow />}
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

// ── Styles ───────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  timeline: {
    flex: 1,
    overflowY: 'auto',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },

  // Empty state
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '16px',
    color: 'var(--text-muted)',
    padding: '40px 32px',
  },
  emptyGlyphs: {
    display: 'flex',
    gap: '14px',
    marginBottom: '4px',
  },
  emptyTitle: {
    fontSize: '18px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    margin: 0,
    letterSpacing: '-0.2px',
  },
  emptyText: {
    fontSize: '13px',
    maxWidth: '340px',
    textAlign: 'center',
    lineHeight: '1.65',
    margin: 0,
    color: 'var(--text-secondary)',
  },
  seedRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    marginTop: '8px',
    width: '100%',
    maxWidth: '340px',
  },
  seedBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '9px 14px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-hairline)',
    background: 'var(--surface-panel)',
    color: 'var(--text-secondary)',
    fontSize: '13px',
    fontWeight: 500,
    cursor: 'pointer',
    textAlign: 'left',
    boxShadow: 'var(--shadow-xs)',
    transition: 'background 0.12s',
  },

  // Processing indicator
  processingRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '10px 14px',
    borderRadius: 'var(--radius-md)',
    background: 'var(--surface-sunken)',
    maxWidth: '320px',
    animation: 'fadeIn 0.2s ease',
  },
  processingText: {
    fontSize: '12px',
    color: 'var(--text-muted)',
    fontWeight: 500,
    marginLeft: '2px',
  },
  dotBlink: {
    display: 'inline-flex',
    gap: '1px',
    fontSize: '14px',
    color: 'var(--text-faint)',
    fontWeight: 700,
    lineHeight: 1,
  },

  // Agent bubble
  bubble: {
    padding: '12px 16px',
    background: 'var(--surface-panel)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-hairline)',
    alignSelf: 'flex-start',
    maxWidth: '85%',
    animation: 'fadeIn 0.2s ease',
    boxShadow: 'var(--shadow-xs)',
  },
  bubbleHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '8px',
  },
  agentName: {
    fontWeight: 600,
    fontSize: '13px',
  },
  addressedTo: {
    fontSize: '11px',
    color: 'var(--brand-link)',
    fontWeight: 500,
  },
  time: {
    fontSize: '11px',
    color: 'var(--text-faint)',
    marginLeft: 'auto',
  },
  content: {
    fontSize: '13px',
    lineHeight: '1.65',
    color: 'var(--text-primary)',
    whiteSpace: 'pre-wrap',
  },
  mention: {
    color: 'var(--brand-link)',
    fontWeight: 600,
  },
  badgeRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '6px',
    marginTop: '10px',
  },
  sourceBadge: {
    padding: '2px 9px',
    borderRadius: 'var(--radius-pill)',
    border: '1px solid var(--border-soft)',
    background: 'var(--surface-sunken)',
    color: 'var(--text-secondary)',
    fontSize: '11px',
    fontWeight: 500,
    cursor: 'pointer',
  },

  // Pass row (minimized)
  passRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '4px 10px',
    opacity: 0.7,
    animation: 'fadeIn 0.2s ease',
  },
  passAgentName: {
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-muted)',
  },
  passContent: {
    fontSize: '12px',
    color: 'var(--text-muted)',
    fontStyle: 'italic',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: '400px',
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
    borderRadius: '14px 14px 4px 14px',
    maxWidth: '75%',
    boxShadow: 'var(--shadow-sm)',
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
  userTime: {
    fontSize: '11px',
    color: 'rgba(255,255,255,0.55)',
  },
  userContent: {
    fontSize: '13px',
    lineHeight: '1.65',
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

  // Session footer (CaseCompletion style)
  sessionFooter: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    padding: '14px 16px',
    marginTop: '4px',
    background: 'var(--surface-panel)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-soft)',
    boxShadow: 'var(--shadow-sm)',
    animation: 'fadeIn 0.2s ease',
  },
  footerHeaderRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  footerSparkleIcon: {
    width: '24px',
    height: '24px',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--brand-primary)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  footerTitle: {
    fontSize: '13px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  footerStats: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexWrap: 'wrap',
  },
  statPill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '3px 10px',
    borderRadius: 'var(--radius-pill)',
    border: '1px solid var(--border-hairline)',
    background: 'var(--surface-sunken)',
  },
  statLabel: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  statValue: {
    fontSize: '12px',
    color: 'var(--text-primary)',
    fontWeight: 700,
  },
  footerFeedback: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    paddingTop: '10px',
    borderTop: '1px solid var(--border-hairline)',
    flexWrap: 'wrap',
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
    padding: '5px 14px',
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
    background: 'var(--surface-sunken)',
    color: 'var(--text-secondary)',
    borderColor: 'var(--border-soft)',
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
};
