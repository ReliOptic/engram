import { useEffect, useState } from 'react';
import { useToast } from '../Toast';
import { Skeleton } from '../Skeleton';

interface RoleConfig {
  provider: string;
  model: string;
}

interface ModelsData {
  providers: Record<string, { base_url: string }>;
  roles: Record<string, RoleConfig>;
}

export function ModelSettings() {
  const [data, setData] = useState<ModelsData | null>(null);
  const [editing, setEditing] = useState<Record<string, RoleConfig>>({});
  const [saving, setSaving] = useState(false);
  const { addToast } = useToast();

  useEffect(() => {
    fetch('/api/settings/models')
      .then((r) => r.json())
      .then((d: ModelsData) => {
        setData(d);
        setEditing(JSON.parse(JSON.stringify(d.roles)));
      })
      .catch(() => addToast('Failed to load model config', 'error'));
  }, [addToast]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const resp = await fetch('/api/settings/models', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roles: editing }),
      });
      if (resp.ok) {
        addToast('Model settings saved', 'success');
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
    return <Skeleton height="40px" count={4} gap="12px" />;
  }

  const providers = Object.keys(data.providers);

  return (
    <div>
      <h2 style={styles.heading}>Model Assignments</h2>
      <p style={styles.description}>Configure which LLM model each agent role uses.</p>

      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Role</th>
            <th style={styles.th}>Provider</th>
            <th style={styles.th}>Model</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(editing).map(([role, config]) => (
            <tr key={role}>
              <td style={styles.td}>
                <span style={styles.roleName}>{role}</span>
              </td>
              <td style={styles.td}>
                <select
                  style={styles.select}
                  value={config.provider}
                  onChange={(e) =>
                    setEditing((prev) => ({
                      ...prev,
                      [role]: { ...prev[role], provider: e.target.value },
                    }))
                  }
                >
                  {providers.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </td>
              <td style={styles.td}>
                <input
                  style={styles.input}
                  value={config.model}
                  onChange={(e) =>
                    setEditing((prev) => ({
                      ...prev,
                      [role]: { ...prev[role], model: e.target.value },
                    }))
                  }
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <button style={styles.saveBtn} onClick={handleSave} disabled={saving}>
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
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    marginBottom: '16px',
  },
  th: {
    textAlign: 'left',
    padding: '8px 12px',
    fontSize: '11px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    color: 'var(--text-muted)',
    borderBottom: '1px solid var(--border-light)',
  },
  td: {
    padding: '8px 12px',
    borderBottom: '1px solid var(--border-light)',
  },
  roleName: {
    fontSize: '13px',
    fontWeight: 500,
    color: 'var(--text-primary)',
    textTransform: 'capitalize',
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
    width: '100%',
  },
  input: {
    padding: '6px 10px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-medium)',
    background: 'var(--bg-primary)',
    fontSize: '12px',
    fontFamily: 'var(--font-family)',
    color: 'var(--text-primary)',
    outline: 'none',
    width: '100%',
  },
  saveBtn: {
    padding: '8px 20px',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    background: 'var(--zeiss-blue)',
    color: 'var(--text-on-dark)',
    fontSize: '13px',
    fontWeight: 600,
    fontFamily: 'var(--font-family)',
    cursor: 'pointer',
    transition: 'opacity 0.15s',
  },
};
