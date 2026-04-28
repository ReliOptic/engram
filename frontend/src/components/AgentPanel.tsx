import type { AgentInfo, AgentStatus } from '../types';

const AGENT_META = {
  analyzer: { name: 'Analyzer', glyph: 'A', color: 'var(--agent-analyzer)', soft: 'var(--agent-analyzer-soft)', role: 'Root-cause analysis', tone: 'Analytical' },
  finder:   { name: 'Finder',   glyph: 'F', color: 'var(--agent-finder)',   soft: 'var(--agent-finder-soft)',   role: 'Knowledge search',    tone: 'Investigative' },
  reviewer: { name: 'Reviewer', glyph: 'R', color: 'var(--agent-reviewer)', soft: 'var(--agent-reviewer-soft)', role: 'Procedure review',     tone: 'Deliberative' },
} as const;

type AgentRole = keyof typeof AGENT_META;

const AGENT_LIST: AgentRole[] = ['analyzer', 'finder', 'reviewer'];

// Minimal inline SVG icons
function Icon({ name, size = 14, stroke = 'currentColor', strokeWidth = 1.6 }: {
  name: string; size?: number; stroke?: string; strokeWidth?: number;
}) {
  const common = {
    width: size, height: size, viewBox: '0 0 24 24' as const,
    fill: 'none' as const, stroke, strokeWidth,
    strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const,
  };
  switch (name) {
    case 'wave':   return <svg {...common}><path d="M3 12c2 0 2-4 4-4s2 8 4 8 2-8 4-8 2 4 4 4"/></svg>;
    case 'search': return <svg {...common}><circle cx="11" cy="11" r="6"/><path d="M20 20l-4-4"/></svg>;
    case 'check':  return <svg {...common}><path d="M5 12l4 4 10-10"/></svg>;
    default:       return null;
  }
}

function AgentGlyph({ role, size = 32, active = false, done = false }: {
  role: AgentRole; size?: number; active?: boolean; done?: boolean;
}) {
  const meta = AGENT_META[role];
  const radius = role === 'finder' ? '50%' : role === 'analyzer' ? 'var(--radius-sm)' : 'var(--radius-xs)';
  const symbolMap: Record<AgentRole, React.ReactNode> = {
    analyzer: <Icon name="wave"   size={Math.round(size * 0.55)} stroke="white" strokeWidth={2} />,
    finder:   <Icon name="search" size={Math.round(size * 0.55)} stroke="white" strokeWidth={2} />,
    reviewer: <Icon name="check"  size={Math.round(size * 0.55)} stroke="white" strokeWidth={2.4} />,
  };
  return (
    <div style={{ position: 'relative', flexShrink: 0, width: size, height: size }}>
      {active && (
        <span style={{
          position: 'absolute', inset: -3,
          borderRadius: role === 'finder' ? '50%' : 'var(--radius-md)',
          border: `2px solid ${meta.color}`, opacity: 0.35,
          animation: 'ringExpand 1.6s ease-out infinite',
        }} />
      )}
      <div style={{
        width: size, height: size, borderRadius: radius,
        background: meta.color,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: active ? `0 0 0 3px ${meta.soft}` : 'none',
      }}>
        {symbolMap[role]}
      </div>
      {done && (
        <div style={{
          position: 'absolute', right: -4, bottom: -4,
          width: Math.round(size * 0.45), height: Math.round(size * 0.45),
          borderRadius: '50%',
          background: 'var(--color-success)', color: 'white',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: '2px solid var(--surface-panel)',
        }}>
          <Icon name="check" size={Math.round(size * 0.25)} stroke="white" strokeWidth={3} />
        </div>
      )}
    </div>
  );
}

function StatusLabel({ status }: { status: AgentStatus }) {
  const map: Record<AgentStatus, { label: string; fg: string }> = {
    idle:       { label: 'Standby',  fg: 'var(--text-muted)' },
    thinking:   { label: 'Working',  fg: 'var(--brand-primary)' },
    done:       { label: 'Complete', fg: 'var(--color-success-text)' },
    waiting:    { label: 'Waiting',  fg: 'var(--color-warning-text)' },
    processing: { label: 'Working',  fg: 'var(--brand-primary)' },
  };
  const c = map[status] ?? map.idle;
  return (
    <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: c.fg }}>
      {c.label}
    </span>
  );
}

function ThinkingBars({ color }: { color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 12 }}>
      {[0, 1, 2, 3].map((i) => (
        <span key={i} style={{
          width: 2, height: '100%', background: color, borderRadius: 1,
          transformOrigin: 'bottom',
          animation: 'barGrow 0.9s ease-in-out infinite alternate',
          animationDelay: `${i * 0.12}s`,
          opacity: 0.85,
          display: 'block',
        }} />
      ))}
    </div>
  );
}

interface AgentCardProps {
  role: AgentRole;
  status: AgentStatus;
  message?: string;
  count?: number;
}

function AgentCard({ role, status, message, count }: AgentCardProps) {
  const meta = AGENT_META[role];
  const active = status === 'thinking' || status === 'processing';
  const done = status === 'done';

  return (
    <div style={{
      position: 'relative',
      padding: '12px 12px',
      background: 'var(--surface-panel)',
      borderRadius: 'var(--radius-md)',
      border: `1px solid ${active ? meta.color : 'var(--border-hairline)'}`,
      boxShadow: active ? `0 0 0 3px ${meta.soft}` : 'var(--shadow-xs)',
      transition: 'box-shadow 0.2s, border-color 0.2s',
      overflow: 'hidden',
    }}>
      {/* Shimmer bar at top when active */}
      {active && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 2,
          background: 'var(--surface-sunken)', overflow: 'hidden',
        }}>
          <div style={{
            position: 'absolute', inset: 0, width: '40%',
            background: `linear-gradient(90deg, transparent, ${meta.color}, transparent)`,
            animation: 'shimmerLine 1.6s linear infinite',
          }} />
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <AgentGlyph role={role} size={32} active={active} done={done} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{meta.name}</span>
            <StatusLabel status={status} />
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>{meta.role}</div>
        </div>
      </div>

      {/* Status detail row */}
      <div style={{
        marginTop: 10, paddingTop: 10,
        borderTop: '1px dashed var(--border-hairline)',
        display: 'flex', alignItems: 'center', gap: 8,
        minHeight: 22,
      }}>
        {active ? (
          <>
            <ThinkingBars color={meta.color} />
            {message && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{message}</span>}
          </>
        ) : done ? (
          <>
            <Icon name="check" size={12} stroke="var(--color-success-text)" strokeWidth={2.4} />
            {message && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{message}</span>}
            {count != null && (
              <span style={{
                marginLeft: 'auto',
                fontFamily: 'var(--font-mono)',
                fontSize: 11, fontWeight: 600,
                color: meta.color,
                padding: '2px 6px',
                background: meta.soft,
                borderRadius: 'var(--radius-xs)',
              }}>{count}</span>
            )}
          </>
        ) : (
          <span style={{ fontSize: 12, color: 'var(--text-faint)', fontStyle: 'italic' }}>{meta.tone}</span>
        )}
      </div>
    </div>
  );
}

interface AgentPanelProps {
  agentStatuses?: Record<string, AgentStatus>;
  agentMessages?: Record<string, string>;
}

export function AgentPanel({ agentStatuses, agentMessages }: AgentPanelProps) {
  return (
    <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 2px',
      }}>
        <span className="eg-eyebrow">Agents</span>
        <span style={{
          fontSize: 10, color: 'var(--text-muted)',
          display: 'inline-flex', alignItems: 'center', gap: 4,
        }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--color-success)' }} />
          live
        </span>
      </div>
      {AGENT_LIST.map((role) => (
        <AgentCard
          key={role}
          role={role}
          status={agentStatuses?.[role] ?? 'idle'}
          message={agentMessages?.[role]}
        />
      ))}
    </div>
  );
}
