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
  user: 'var(--zeiss-blue)',
};

const AGENT_NAMES: Record<AgentRole, string> = {
  analyzer: 'Analyzer',
  finder: 'Finder',
  reviewer: 'Reviewer',
  user: 'You',
};

export function ChatTimeline({ messages, isProcessing }: ChatTimelineProps) {
  const timelineRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change or processing state changes
  useEffect(() => {
    if (timelineRef.current) {
      timelineRef.current.scrollTop = timelineRef.current.scrollHeight;
    }
  }, [messages, isProcessing]);

  if (messages.length === 0) {
    return (
      <div style={styles.empty}>
        <div style={styles.emptyIcon}>💬</div>
        <p style={styles.emptyText}>
          Start a conversation by describing your EUV equipment issue below.
        </p>
      </div>
    );
  }

  return (
    <div ref={timelineRef} style={styles.timeline}>
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isProcessing && (
        <div style={styles.thinkingRow}>
          <div style={styles.thinkingDots}>
            <span style={styles.dot1} />
            <span style={styles.dot2} />
            <span style={styles.dot3} />
          </div>
          <span style={styles.thinkingText}>Agents are thinking...</span>
        </div>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: AgentMessage }) {
  const isUser = message.agent === 'user';
  const agentColor = AGENT_COLORS[message.agent] ?? 'var(--zeiss-blue)';
  const agentName = AGENT_NAMES[message.agent] ?? message.agent;

  // Highlight @mentions in content
  const renderContent = (text: string) => {
    const parts = text.split(/(@\w+)/g);
    return parts.map((part, i) =>
      part.startsWith('@') ? (
        <span key={i} style={styles.mention}>
          {part}
        </span>
      ) : (
        <span key={i}>{part}</span>
      ),
    );
  };

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
        {message.contributionType && (
          <span style={styles.tag}>{message.contributionType}</span>
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

const styles: Record<string, React.CSSProperties> = {
  timeline: {
    flex: 1,
    overflowY: 'auto',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '12px',
    color: 'var(--text-muted)',
  },
  emptyIcon: {
    fontSize: '48px',
    opacity: 0.4,
  },
  emptyText: {
    fontSize: '14px',
    maxWidth: '300px',
    textAlign: 'center',
    lineHeight: '1.6',
  },
  bubble: {
    padding: '12px 16px',
    background: 'var(--bg-primary)',
    borderRadius: 'var(--radius-lg)',
    border: '1px solid var(--border-light)',
    alignSelf: 'flex-start',
    maxWidth: '85%',
  },
  // User bubble — right-aligned, ZEISS blue
  userBubbleWrapper: {
    display: 'flex',
    justifyContent: 'flex-end',
  },
  userBubble: {
    padding: '12px 16px',
    background: 'var(--zeiss-blue)',
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
    fontWeight: 500,
    padding: '1px 6px',
    borderRadius: 'var(--radius-pill)',
    background: 'var(--bg-secondary)',
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
  },
  addressedTo: {
    fontSize: '11px',
    color: 'var(--zeiss-link)',
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
    color: 'var(--zeiss-link)',
    fontWeight: 600,
  },
  // Thinking indicator
  thinkingRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '8px 16px',
  },
  thinkingDots: {
    display: 'flex',
    gap: '4px',
    alignItems: 'center',
  },
  dot1: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    background: 'var(--agent-analyzer)',
    animation: 'pulse 1.4s infinite',
    animationDelay: '0s',
  },
  dot2: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    background: 'var(--agent-finder)',
    animation: 'pulse 1.4s infinite',
    animationDelay: '0.2s',
  },
  dot3: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    background: 'var(--agent-reviewer)',
    animation: 'pulse 1.4s infinite',
    animationDelay: '0.4s',
  },
  thinkingText: {
    fontSize: '12px',
    color: 'var(--text-muted)',
    fontStyle: 'italic',
  },
};
