import { useMemo, useState } from 'react';
import type { Session } from '../hooks/useSessions';

interface HistorySidebarProps {
  sessions: Session[];
  currentSessionId: string | null;
  onNewChat: () => void;
  onSelect: (sessionId: string) => void;
  onDelete?: (sessionId: string) => void;
  onRename?: (sessionId: string, title: string) => void;
}

function groupByDate(sessions: Session[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: { label: string; items: Session[] }[] = [
    { label: 'Today', items: [] },
    { label: 'Yesterday', items: [] },
    { label: 'Last 7 Days', items: [] },
    { label: 'Older', items: [] },
  ];

  for (const s of sessions) {
    const d = new Date(s.updated_at || s.created_at);
    if (d >= today) groups[0].items.push(s);
    else if (d >= yesterday) groups[1].items.push(s);
    else if (d >= weekAgo) groups[2].items.push(s);
    else groups[3].items.push(s);
  }

  return groups.filter((g) => g.items.length > 0);
}

function formatTimestamp(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

export function HistorySidebar({
  sessions,
  currentSessionId,
  onNewChat,
  onSelect,
  onDelete,
  onRename,
}: HistorySidebarProps) {
  const [search, setSearch] = useState('');
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameText, setRenameText] = useState('');
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!search.trim()) return sessions;
    const q = search.toLowerCase();
    return sessions.filter(
      (s) =>
        s.title.toLowerCase().includes(q) ||
        s.silo_account.toLowerCase().includes(q) ||
        s.silo_tool.toLowerCase().includes(q),
    );
  }, [sessions, search]);

  const groups = useMemo(() => groupByDate(filtered), [filtered]);

  const handleRenameStart = (session: Session) => {
    setRenaming(session.session_id);
    setRenameText(session.title);
    setMenuOpen(null);
  };

  const handleRenameSubmit = (sessionId: string) => {
    if (renameText.trim()) {
      onRename?.(sessionId, renameText.trim());
    }
    setRenaming(null);
  };

  const handleDeleteRequest = (sessionId: string) => {
    setConfirmDeleteId(sessionId);
  };

  const handleDeleteConfirm = (sessionId: string) => {
    onDelete?.(sessionId);
    setConfirmDeleteId(null);
    setMenuOpen(null);
  };

  const handleDeleteCancel = () => {
    setConfirmDeleteId(null);
  };

  return (
    <div style={styles.sidebar}>
      {/* Header row */}
      <div style={styles.headerRow}>
        <span style={styles.eyebrow}>HISTORY</span>
        <button style={styles.newBtn} onClick={onNewChat} title="New chat">
          <PlusIcon />
          <span>New</span>
        </button>
      </div>

      {/* Search */}
      <input
        style={styles.searchInput}
        type="text"
        placeholder="Search chats..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {/* Session list */}
      <div style={styles.list}>
        {groups.length === 0 && (
          <p style={styles.emptyText}>
            {sessions.length === 0 ? 'No conversations yet. Start chatting!' : 'No results found.'}
          </p>
        )}

        {groups.map((group) => (
          <div key={group.label}>
            <div style={styles.groupLabel}>{group.label}</div>
            {group.items.map((session) => {
              const isHovered = hoveredId === session.session_id;
              const isActive = session.session_id === currentSessionId;
              const ts = formatTimestamp(session.updated_at || session.created_at);

              return (
                <button
                  key={session.session_id}
                  style={{
                    ...styles.item,
                    ...(isActive ? styles.itemActive : {}),
                    ...(isHovered && !isActive ? styles.itemHover : {}),
                  }}
                  onClick={() => onSelect(session.session_id)}
                  onMouseEnter={() => setHoveredId(session.session_id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setMenuOpen(menuOpen === session.session_id ? null : session.session_id);
                  }}
                >
                  {renaming === session.session_id ? (
                    <input
                      style={styles.renameInput}
                      value={renameText}
                      onChange={(e) => setRenameText(e.target.value)}
                      onBlur={() => handleRenameSubmit(session.session_id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRenameSubmit(session.session_id);
                        if (e.key === 'Escape') setRenaming(null);
                      }}
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <div style={styles.itemInner}>
                      {/* First line: dot + title + timestamp */}
                      <div style={styles.itemFirstLine}>
                        <span
                          style={{
                            ...styles.activeDot,
                            backgroundColor: isActive
                              ? 'var(--brand-primary)'
                              : 'var(--border-medium)',
                          }}
                          className={isActive ? 'pulse-dot' : undefined}
                        />
                        <span style={styles.itemTitle}>{session.title || 'Untitled'}</span>
                        <span style={styles.itemTimestamp}>{ts}</span>
                      </div>
                      {/* Second line: preview */}
                      <div style={styles.itemPreview}>
                        {session.silo_account
                          ? `${session.silo_account} · ${session.silo_tool}`
                          : `${session.message_count} msg${session.message_count !== 1 ? 's' : ''}`}
                      </div>
                    </div>
                  )}

                  {/* Menu trigger */}
                  <button
                    style={{
                      ...styles.menuBtn,
                      opacity: isHovered || menuOpen === session.session_id ? 1 : 0,
                      pointerEvents:
                        isHovered || menuOpen === session.session_id ? 'auto' : 'none',
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(menuOpen === session.session_id ? null : session.session_id);
                    }}
                  >
                    ···
                  </button>

                  {/* Dropdown menu */}
                  {menuOpen === session.session_id && (
                    <div style={styles.menu}>
                      <button
                        style={styles.menuItem}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRenameStart(session);
                        }}
                      >
                        Rename
                      </button>
                      {confirmDeleteId === session.session_id ? (
                        <div style={styles.confirmRow}>
                          <span style={styles.confirmLabel}>Delete?</span>
                          <button
                            style={{ ...styles.confirmBtn, ...styles.confirmBtnDanger }}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteConfirm(session.session_id);
                            }}
                          >
                            Yes
                          </button>
                          <button
                            style={{ ...styles.confirmBtn, ...styles.confirmBtnCancel }}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteCancel();
                            }}
                          >
                            No
                          </button>
                        </div>
                      ) : (
                        <button
                          style={{ ...styles.menuItem, color: 'var(--color-error)' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteRequest(session.session_id);
                          }}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function PlusIcon() {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    >
      <path d="M7 1V13M1 7H13" />
    </svg>
  );
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    padding: '10px 10px 12px',
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    gap: '8px',
    boxSizing: 'border-box',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '2px',
  },
  eyebrow: {
    fontSize: '10px',
    fontWeight: 700,
    letterSpacing: '1.2px',
    color: 'var(--text-faint)',
    fontFamily: 'var(--font-mono)',
  },
  newBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 9px',
    borderRadius: 'var(--radius-pill)',
    border: '1px solid var(--border-hairline)',
    background: 'transparent',
    color: 'var(--brand-primary)',
    fontSize: '11px',
    fontWeight: 600,
    fontFamily: 'var(--font-family)',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
  searchInput: {
    padding: '6px 10px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-hairline)',
    background: 'var(--surface-sunken)',
    fontSize: '12px',
    fontFamily: 'var(--font-family)',
    color: 'var(--text-primary)',
    outline: 'none',
    flexShrink: 0,
    width: '100%',
    boxSizing: 'border-box',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
  },
  emptyText: {
    fontSize: '12px',
    color: 'var(--text-muted)',
    lineHeight: '1.6',
    padding: '8px 4px',
    margin: 0,
  },
  groupLabel: {
    fontSize: '10px',
    fontWeight: 600,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.8px',
    color: 'var(--text-faint)',
    padding: '6px 10px',
    fontFamily: 'var(--font-mono)',
  },
  item: {
    position: 'relative',
    width: '100%',
    padding: '7px 10px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid transparent',
    cursor: 'pointer',
    transition: 'background 0.1s, border-color 0.1s',
    display: 'flex',
    alignItems: 'flex-start',
    gap: '4px',
    background: 'transparent',
    textAlign: 'left' as const,
    fontFamily: 'var(--font-family)',
    boxSizing: 'border-box',
  },
  itemActive: {
    background: 'var(--surface-panel)',
    border: '1px solid var(--border-hairline)',
    boxShadow: 'var(--shadow-xs)',
  },
  itemHover: {
    background: 'var(--surface-hover)',
  },
  itemInner: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  itemFirstLine: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  activeDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    flexShrink: 0,
    transition: 'background-color 0.2s',
  },
  itemTitle: {
    fontSize: '12px',
    fontWeight: 500,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
    flex: 1,
    minWidth: 0,
  },
  itemTimestamp: {
    fontSize: '10px',
    color: 'var(--text-faint)',
    fontFamily: 'var(--font-mono)',
    flexShrink: 0,
    whiteSpace: 'nowrap' as const,
  },
  itemPreview: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
    paddingLeft: '12px',
  },
  renameInput: {
    flex: 1,
    padding: '2px 6px',
    fontSize: '12px',
    fontFamily: 'var(--font-family)',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--brand-primary)',
    outline: 'none',
    background: 'var(--surface-panel)',
    color: 'var(--text-primary)',
  },
  menuBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    padding: '0 4px',
    lineHeight: 1,
    flexShrink: 0,
    transition: 'opacity 0.15s',
    letterSpacing: '1px',
  },
  menu: {
    position: 'absolute',
    right: '4px',
    top: '100%',
    background: 'var(--surface-panel)',
    border: '1px solid var(--border-hairline)',
    borderRadius: 'var(--radius-md)',
    boxShadow: 'var(--shadow-md)',
    zIndex: 10,
    overflow: 'hidden',
    minWidth: '120px',
  },
  menuItem: {
    display: 'block',
    width: '100%',
    padding: '6px 12px',
    fontSize: '12px',
    fontFamily: 'var(--font-family)',
    color: 'var(--text-primary)',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    textAlign: 'left' as const,
    transition: 'background 0.1s',
  },
  confirmRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    padding: '5px 12px',
  },
  confirmLabel: {
    fontSize: '11px',
    color: 'var(--text-secondary)',
    flex: 1,
  },
  confirmBtn: {
    fontSize: '11px',
    fontWeight: 600,
    fontFamily: 'var(--font-family)',
    border: 'none',
    borderRadius: 'var(--radius-sm)',
    padding: '3px 8px',
    cursor: 'pointer',
  },
  confirmBtnDanger: {
    background: 'var(--color-error)',
    color: 'white',
  },
  confirmBtnCancel: {
    background: 'var(--surface-sunken)',
    color: 'var(--text-secondary)',
  },
};
