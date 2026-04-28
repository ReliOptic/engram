import { useEffect, useRef, useState } from 'react';
import type { DropdownConfig, SiloSelection } from '../types';

interface UploadedFile {
  filename: string;
  saved_as: string;
  size_bytes: number;
  extracted_text?: string;
}

interface ChatInputProps {
  onSend: (message: string, silo: SiloSelection, attachments?: UploadedFile[]) => void;
  disabled?: boolean;
  isProcessing?: boolean;
  onStop?: () => void;
}

export function ChatInput({ onSend, disabled, isProcessing, onStop }: ChatInputProps) {
  const [text, setText] = useState('');
  const [dropdowns, setDropdowns] = useState<DropdownConfig | null>(null);
  const [silo, setSilo] = useState<SiloSelection>({ account: '', tool: '', component: '' });
  const [attachments, setAttachments] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [scopeOpen, setScopeOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch('/api/config/dropdowns')
      .then((r) => r.json())
      .then((data: DropdownConfig) => {
        setDropdowns(data);
        const firstAccount = Object.keys(data.accounts)[0] ?? '';
        const firstTool = firstAccount ? Object.keys(data.accounts[firstAccount].tools)[0] ?? '' : '';
        const firstComponent =
          firstAccount && firstTool
            ? data.accounts[firstAccount].tools[firstTool].components[0] ?? ''
            : '';
        setSilo({ account: firstAccount, tool: firstTool, component: firstComponent });
      })
      .catch(() => {
        const mock: DropdownConfig = {
          accounts: {
            'Demo Client': {
              tools: {
                'Product A': { components: ['Module 1', 'Module 2', 'Module 3'] },
                'Product B': { components: ['Module 1', 'Module 2'] },
              },
            },
          },
        };
        setDropdowns(mock);
        setSilo({ account: 'Demo Client', tool: 'Product A', component: 'Module 1' });
      });
  }, []);

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(Math.max(el.scrollHeight, 40), 160)}px`;
    }
  };

  const accounts = dropdowns ? Object.keys(dropdowns.accounts) : [];
  const tools =
    silo.account && dropdowns ? Object.keys(dropdowns.accounts[silo.account]?.tools ?? {}) : [];
  const components =
    silo.account && silo.tool && dropdowns
      ? dropdowns.accounts[silo.account]?.tools[silo.tool]?.components ?? []
      : [];

  const handleAccountChange = (account: string) => {
    const newTools = dropdowns ? Object.keys(dropdowns.accounts[account]?.tools ?? {}) : [];
    const newTool = newTools[0] ?? '';
    const newComponents =
      dropdowns && account && newTool
        ? dropdowns.accounts[account].tools[newTool]?.components ?? []
        : [];
    setSilo({ account, tool: newTool, component: newComponents[0] ?? '' });
  };

  const handleToolChange = (tool: string) => {
    const newComponents =
      dropdowns && silo.account && tool
        ? dropdowns.accounts[silo.account].tools[tool]?.components ?? []
        : [];
    setSilo({ ...silo, tool, component: newComponents[0] ?? '' });
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const formData = new FormData();
        formData.append('file', file);
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        if (res.ok) {
          const result: UploadedFile = await res.json();
          setAttachments((prev) => [...prev, result]);
        }
      }
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const removeAttachment = (idx: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = () => {
    if ((!text.trim() && attachments.length === 0) || !silo.account) return;
    onSend(text.trim(), silo, attachments.length > 0 ? attachments : undefined);
    setText('');
    setAttachments([]);
    if (textareaRef.current) textareaRef.current.style.height = '40px';
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const canSend = (!!text.trim() || attachments.length > 0) && !disabled;

  const scopeLabel = (() => {
    const a = silo.account ? `account/${silo.account}` : 'account/—';
    const t = silo.tool ? `tool/${silo.tool}` : 'tool/—';
    const c = silo.component ? `component/${silo.component}` : 'component/—';
    return `${a} · ${t} · ${c}`;
  })();

  const inputBorderStyle: React.CSSProperties = canSend
    ? { border: '1px solid var(--brand-primary)', boxShadow: 'var(--shadow-glow-brand)' }
    : { border: '1px solid var(--border-soft)', boxShadow: 'none' };

  return (
    <div style={styles.container}>
      {/* SCOPE row */}
      <div style={styles.scopeRow}>
        <span style={styles.scopeEyebrow}>SCOPE</span>
        <button
          style={styles.scopePill}
          onClick={() => setScopeOpen((v) => !v)}
          title="Configure scope"
        >
          <span style={styles.scopePillText}>{scopeLabel}</span>
          <ChevronDownIcon />
        </button>
        <span style={styles.statusText}>
          {isProcessing ? 'Agents are reasoning…' : 'Ready'}
        </span>
      </div>

      {/* Cascading dropdowns — shown when scopeOpen */}
      {scopeOpen && (
        <div style={styles.dropdownRow}>
          <select
            style={styles.select}
            value={silo.account}
            onChange={(e) => handleAccountChange(e.target.value)}
          >
            <option value="" disabled>Account</option>
            {accounts.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
          <select
            style={styles.select}
            value={silo.tool}
            onChange={(e) => handleToolChange(e.target.value)}
            disabled={!silo.account}
          >
            <option value="" disabled>Tool</option>
            {tools.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <select
            style={styles.select}
            value={silo.component}
            onChange={(e) => setSilo({ ...silo, component: e.target.value })}
            disabled={!silo.tool}
          >
            <option value="" disabled>Component</option>
            {components.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
      )}

      {/* Attachment chips */}
      {attachments.length > 0 && (
        <div style={styles.attachRow}>
          {attachments.map((a, i) => (
            <span key={i} style={styles.attachChip}>
              <span style={styles.attachLabel}>[img]</span>
              {a.filename} ({(a.size_bytes / 1024).toFixed(1)}KB)
              {a.extracted_text && (
                <span style={styles.attachOcrPreview}>
                  &ldquo;{a.extracted_text.slice(0, 80)}{a.extracted_text.length > 80 ? '…' : ''}&rdquo;
                </span>
              )}
              <button style={styles.attachRemove} onClick={() => removeAttachment(i)}>
                &times;
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Unified input container */}
      <div style={{ ...styles.inputContainer, ...inputBorderStyle }}>
        <input
          ref={fileInputRef}
          type="file"
          style={{ display: 'none' }}
          onChange={handleFileUpload}
          multiple
        />
        <button
          style={styles.clipBtn}
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading || disabled}
          title="Attach file"
        >
          {uploading ? (
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>…</span>
          ) : (
            <ClipIcon />
          )}
        </button>

        <textarea
          ref={textareaRef}
          style={styles.textarea}
          placeholder="Describe your issue..."
          value={text}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />

        {isProcessing ? (
          <button style={styles.stopBtn} onClick={onStop}>
            <CheckIcon />
            <span>Stop</span>
          </button>
        ) : (
          <button
            style={{
              ...styles.sendBtn,
              ...(canSend ? styles.sendBtnActive : styles.sendBtnInactive),
            }}
            onClick={handleSubmit}
            disabled={!canSend}
          >
            <SendIcon />
            <span>Send</span>
            <span style={styles.sendHint}>⏎</span>
          </button>
        )}
      </div>
    </div>
  );
}

function ClipIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66L9.41 17.41A2 2 0 016.59 14.6l8.49-8.48" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: '10px 14px 12px',
    borderTop: '1px solid var(--border-hairline)',
    background: 'var(--surface-panel)',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  scopeRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  scopeEyebrow: {
    fontSize: '10px',
    fontWeight: 700,
    letterSpacing: '1px',
    color: 'var(--text-faint)',
    fontFamily: 'var(--font-mono)',
    flexShrink: 0,
  },
  scopePill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '3px 10px',
    borderRadius: 'var(--radius-pill)',
    border: '1px solid var(--border-hairline)',
    background: 'var(--surface-sunken)',
    fontSize: '11px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    flexShrink: 1,
    minWidth: 0,
    overflow: 'hidden',
  },
  scopePillText: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  statusText: {
    fontSize: '11px',
    color: 'var(--text-faint)',
    fontFamily: 'var(--font-mono)',
    marginLeft: 'auto',
    flexShrink: 0,
    whiteSpace: 'nowrap' as const,
  },
  dropdownRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  select: {
    padding: '6px 10px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-medium)',
    background: 'var(--surface-panel)',
    fontSize: '12px',
    fontFamily: 'var(--font-family)',
    color: 'var(--text-primary)',
    outline: 'none',
    cursor: 'pointer',
    flex: 1,
    minWidth: 0,
  },
  attachRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '6px',
  },
  attachChip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 8px',
    borderRadius: 'var(--radius-pill)',
    background: 'var(--surface-sunken)',
    fontSize: '11px',
    color: 'var(--text-secondary)',
  },
  attachLabel: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    fontWeight: 600,
    marginRight: '4px',
  },
  attachOcrPreview: {
    display: 'block',
    fontSize: '10px',
    color: 'var(--text-muted)',
    fontStyle: 'italic',
    marginTop: '2px',
    lineHeight: '1.3',
  },
  attachRemove: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: '13px',
    color: 'var(--text-muted)',
    padding: '0 2px',
    lineHeight: 1,
  },
  inputContainer: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: '4px',
    borderRadius: 'var(--radius-md)',
    padding: '6px 8px',
    background: 'var(--surface-panel)',
    transition: 'border-color 0.15s, box-shadow 0.15s',
  },
  clipBtn: {
    width: '32px',
    height: '32px',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    background: 'transparent',
    color: 'var(--text-muted)',
    cursor: 'pointer',
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'color 0.15s',
  },
  textarea: {
    flex: 1,
    padding: '6px 4px',
    border: 'none',
    background: 'transparent',
    fontSize: '13px',
    fontFamily: 'var(--font-family)',
    color: 'var(--text-primary)',
    resize: 'none',
    outline: 'none',
    lineHeight: '1.5',
    minHeight: '40px',
    maxHeight: '160px',
    overflowY: 'auto',
  },
  sendBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '7px 14px',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'var(--font-family)',
    flexShrink: 0,
    transition: 'background 0.15s, color 0.15s, opacity 0.15s',
    cursor: 'pointer',
  },
  sendBtnActive: {
    background: 'var(--brand-primary)',
    color: '#FFFFFF',
  },
  sendBtnInactive: {
    background: 'var(--surface-sunken)',
    color: 'var(--text-muted)',
    cursor: 'not-allowed',
  },
  sendHint: {
    fontFamily: 'var(--font-mono)',
    fontSize: '11px',
    opacity: 0.6,
  },
  stopBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '7px 14px',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    background: 'var(--surface-sunken)',
    color: 'var(--text-secondary)',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'var(--font-family)',
    cursor: 'pointer',
    flexShrink: 0,
    transition: 'background 0.15s',
  },
};
