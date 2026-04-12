import { useEffect, useState } from 'react';
import { useToast } from '../Toast';
import { Skeleton } from '../Skeleton';

interface DropdownConfig {
  accounts: Record<string, {
    tools: Record<string, {
      components: string[];
    }>;
  }>;
}

export function DropdownSettings() {
  const [data, setData] = useState<DropdownConfig | null>(null);
  const [jsonText, setJsonText] = useState('');
  const [parseError, setParseError] = useState('');
  const [saving, setSaving] = useState(false);
  const { addToast } = useToast();

  useEffect(() => {
    fetch('/api/config/dropdowns')
      .then((r) => r.json())
      .then((d: DropdownConfig) => {
        setData(d);
        setJsonText(JSON.stringify(d, null, 2));
      })
      .catch(() => addToast('Failed to load dropdown config', 'error'));
  }, [addToast]);

  const handleJsonChange = (value: string) => {
    setJsonText(value);
    try {
      JSON.parse(value);
      setParseError('');
    } catch (e) {
      setParseError(String(e));
    }
  };

  const handleSave = async () => {
    let parsed: DropdownConfig;
    try {
      parsed = JSON.parse(jsonText);
    } catch {
      addToast('Invalid JSON', 'error');
      return;
    }

    if (!parsed.accounts) {
      addToast('JSON must have "accounts" key', 'error');
      return;
    }

    setSaving(true);
    try {
      const resp = await fetch('/api/settings/dropdowns', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: jsonText,
      });
      if (resp.ok) {
        setData(parsed);
        addToast('Dropdown config saved', 'success');
      } else {
        addToast('Failed to save', 'error');
      }
    } catch {
      addToast('Network error', 'error');
    } finally {
      setSaving(false);
    }
  };

  if (!data) {
    return <Skeleton height="200px" count={1} />;
  }

  return (
    <div>
      <h2 style={styles.heading}>Dropdown Configuration</h2>
      <p style={styles.description}>
        Edit the Account / Tool / Component hierarchy used in the chat input.
      </p>

      {/* Tree preview */}
      <div style={styles.treeContainer}>
        {Object.entries(data.accounts).map(([account, acctData]) => (
          <div key={account} style={styles.treeNode}>
            <span style={styles.treeLabel}>{account}</span>
            {Object.entries(acctData.tools).map(([tool, toolData]) => (
              <div key={tool} style={{ ...styles.treeNode, marginLeft: '16px' }}>
                <span style={styles.treeLabel}>{tool}</span>
                <div style={{ marginLeft: '16px', display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                  {toolData.components.map((comp) => (
                    <span key={comp} style={styles.chip}>{comp}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* JSON editor */}
      <div style={styles.editorContainer}>
        <label style={styles.editorLabel}>JSON Editor</label>
        <textarea
          style={{
            ...styles.textarea,
            borderColor: parseError ? 'var(--color-error)' : 'var(--border-medium)',
          }}
          value={jsonText}
          onChange={(e) => handleJsonChange(e.target.value)}
          rows={15}
        />
        {parseError && <span style={styles.errorText}>Invalid JSON</span>}
      </div>

      <button style={styles.saveBtn} onClick={handleSave} disabled={saving || !!parseError}>
        {saving ? 'Saving...' : 'Save Changes'}
      </button>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  heading: {
    fontSize: '16px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: '4px',
  },
  description: {
    fontSize: '13px',
    color: 'var(--text-secondary)',
    marginBottom: '20px',
  },
  treeContainer: {
    padding: '16px',
    background: 'var(--bg-primary)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-light)',
    marginBottom: '20px',
  },
  treeNode: {
    marginBottom: '8px',
  },
  treeLabel: {
    fontSize: '13px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    display: 'block',
    marginBottom: '4px',
  },
  chip: {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 'var(--radius-pill)',
    background: 'var(--bg-secondary)',
    fontSize: '11px',
    color: 'var(--text-secondary)',
    fontWeight: 500,
  },
  editorContainer: {
    marginBottom: '16px',
  },
  editorLabel: {
    display: 'block',
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: '6px',
  },
  textarea: {
    width: '100%',
    padding: '12px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-medium)',
    background: 'var(--bg-primary)',
    fontSize: '12px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-primary)',
    resize: 'vertical',
    outline: 'none',
    lineHeight: '1.5',
  },
  errorText: {
    fontSize: '11px',
    color: 'var(--color-error)',
    marginTop: '4px',
    display: 'block',
  },
  saveBtn: {
    padding: '8px 20px',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    background: 'var(--brand-primary)',
    color: 'var(--text-on-dark)',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'var(--font-family)',
    cursor: 'pointer',
    transition: 'opacity 0.15s',
  },
};
