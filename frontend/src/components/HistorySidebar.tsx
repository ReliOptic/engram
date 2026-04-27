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
  const [newChatHovered, setNewChatHovered] = useState(false);

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
      {/* New Chat button */}
      <button
        style={{
          ...styles.newChatBtn,
          ...(newChatHovered ? styles.newChatBtnHover : {}),
        }}
        onClick={onNewChat}
        onMouseEnter={() => setNewChatHovered(true)}
        onMouseLeave={() => setNewChatHovered(false)}
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ marginRight: 6 }}>
          <path d="M7 1V13M1 7H13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        New Chat
      </button>

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
            {sessions.length === 0
              ? 'No conversations yet. Start chatting!'
              : 'No results found.'}
          </p>
        )}

        {groups.map((group) => (
          <div key={group.label}>
            <div style={styles.groupLabel}>{group.label}</div>
            {group.items.map((session) => {
              const isHovered = hoveredId === session.session_id;
              const isActive = session.session_id === currentSessionId;

              return (
                <div
                  key={session.session_id}
                  style={{
                    ...styles.item,
                    ...(isActive ? styles.itemActive : {}),
                    ...(isHovered && !isActive ? styles.itemHover : {}),
                  }}
                  onClick={() => onSelect(session.session_id)}
                  onMouseEnter={() => setHoveredId(session.session_id)}
                  onMouseLeave={() => {
                    setHoveredId(null);
                    if (menuOpen === session.session_id) {
                      // keep menu open if user moved to it
                    }
                  }}
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
                    <div style={styles.itemContent}>
                      <span style={styles.itemTitle}>{session.title || 'Untitled'}</span>
                      <span style={styles.itemMeta}>
                        {session.message_count} msg{session.message_count !== 1 ? 's' : ''}
                        {session.silo_account ? ` · ${session.silo_account}` : ''}
                      </span>
                    </div>
                  )}

                  {/* Menu trigger — visible only on hover */}
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
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    gap: '8px',
  },
  newChatBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '8px 12px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-medium)',
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'var(--font-family)',
    cursor: 'pointer',
    transition: 'background 0.15s, border-color 0.15s, color 0.15s',
    flexShrink: 0,
  },
  newChatBtnHover: {
    background: 'var(--brand-primary)',
    color: 'white',
    borderColor: 'var(--brand-primary)',
  },
  searchInput: {
    padding: '6px 10px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-light)',
    background: 'var(--bg-primary)',
    fontSize: '12px',
    fontFamily: 'var(--font-family)',
    color: 'var(--text-primary)',
    outline: 'none',
    flexShrink: 0,
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
  },
  groupLabel: {
    fontSize: '11px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    color: 'var(--text-muted)',
    padding: '8px 4px 4px',
  },
  item: {
    position: 'relative',
    padding: '8px 10px',
    borderRadius: 'var(--radius-md)',
    cursor: 'pointer',
    transition: 'background 0.1s',
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  itemActive: {
    background: 'var(--bg-hover)',
  },
  itemHover: {
    background: 'var(--bg-secondary)',
  },
  itemContent: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
  },
  itemTitle: {
    fontSize: '12px',
    fontWeight: 500,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  itemMeta: {
    fontSize: '11px',
    color: 'var(--text-muted)',
  },
  renameInput: {
    flex: 1,
    padding: '2px 6px',
    fontSize: '12px',
    fontFamily: 'var(--font-family)',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--brand-primary)',
    outline: 'none',
    background: 'var(--bg-primary)',
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
    background: 'var(--bg-primary)',
    border: '1px solid var(--border-light)',
    borderRadius: 'var(--radius-md)',
    boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
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
    textAlign: 'left',
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
    background: 'var(--bg-secondary)',
    color: 'var(--text-secondary)',
  },
};
