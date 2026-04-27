import { useEffect, useRef, useState } from 'react';
import type { DropdownConfig, SiloSelection } from '../types';

interface UploadedFile {
  filename: string;
  saved_as: string;
  size_bytes: number;
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
  const [silo, setSilo] = useState<SiloSelection>({
    account: '',
    tool: '',
    component: '',
  });
  const [attachments, setAttachments] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch('/api/config/dropdowns')
      .then((r) => r.json())
      .then((data: DropdownConfig) => {
        setDropdowns(data);
        const firstAccount = Object.keys(data.accounts)[0] ?? '';
        const firstTool = firstAccount
          ? Object.keys(data.accounts[firstAccount].tools)[0] ?? ''
          : '';
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

  // Auto-resize textarea: min 40px, max 160px
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
    silo.account && dropdowns
      ? Object.keys(dropdowns.accounts[silo.account]?.tools ?? {})
      : [];
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
    if (!text.trim() || !silo.account) return;
    onSend(text.trim(), silo, attachments.length > 0 ? attachments : undefined);
    setText('');
    setAttachments([]);
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = '40px';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const canSend = !!text.trim() && !disabled;
  const siloLabel =
    silo.account && silo.tool && silo.component
      ? `${silo.account} / ${silo.tool} / ${silo.component}`
      : 'Select context';

  return (
    <div style={styles.container}>
      {/* Cascading dropdown row */}
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

      {/* Silo context tag — own row below dropdowns */}
      <div style={styles.siloTagRow}>
        <span style={styles.siloTag}>{siloLabel}</span>
      </div>

      {/* Attachment chips */}
      {attachments.length > 0 && (
        <div style={styles.attachRow}>
          {attachments.map((a, i) => (
            <span key={i} style={styles.attachChip}>
              {a.filename} ({(a.size_bytes / 1024).toFixed(1)}KB)
              <button style={styles.attachRemove} onClick={() => removeAttachment(i)}>
                &times;
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Text input row */}
      <div style={styles.inputRow}>
        <input
          ref={fileInputRef}
          type="file"
          style={{ display: 'none' }}
          onChange={handleFileUpload}
          multiple
        />
        <button
          style={styles.uploadBtn}
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
            Stop
          </button>
        ) : (
          <button
            style={{
              ...styles.sendBtn,
              opacity: canSend ? 1 : 0.5,
              cursor: canSend ? 'pointer' : 'not-allowed',
            }}
            onClick={handleSubmit}
            disabled={!canSend}
          >
            Send
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

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: '12px 16px',
    borderTop: '1px solid var(--border-light)',
    background: 'var(--bg-primary)',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
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
    background: 'var(--bg-primary)',
    fontSize: '12px',
    fontFamily: 'var(--font-family)',
    color: 'var(--text-primary)',
    outline: 'none',
    cursor: 'pointer',
  },
  siloTagRow: {
    display: 'flex',
    alignItems: 'center',
  },
  siloTag: {
    display: 'inline-block',
    padding: '3px 10px',
    borderRadius: 'var(--radius-pill)',
    background: 'var(--bg-secondary)',
    fontSize: '11px',
    color: 'var(--text-muted)',
    fontWeight: 500,
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
    background: 'var(--bg-secondary)',
    fontSize: '11px',
    color: 'var(--text-secondary)',
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
  inputRow: {
    display: 'flex',
    gap: '8px',
    alignItems: 'flex-end',
  },
  uploadBtn: {
    width: '36px',
    height: '36px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-medium)',
    background: 'var(--bg-secondary)',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  textarea: {
    flex: 1,
    padding: '10px 12px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-medium)',
    background: 'var(--bg-secondary)',
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
    padding: '10px 20px',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    background: 'var(--brand-primary)',
    color: 'var(--text-on-dark)',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'var(--font-family)',
    flexShrink: 0,
    transition: 'opacity 0.15s',
  },
  stopBtn: {
    padding: '10px 20px',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    background: '#DC2626',
    color: '#FFFFFF',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'var(--font-family)',
    cursor: 'pointer',
    flexShrink: 0,
  },
};
