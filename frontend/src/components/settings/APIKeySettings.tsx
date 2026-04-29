import { useState } from 'react';
import { useToast } from '../toast-context';

interface KeyEntry {
  provider: string;
  label: string;
  value: string;
  status: 'untested' | 'testing' | 'valid' | 'invalid';
}

export function APIKeySettings() {
  const [keys, setKeys] = useState<KeyEntry[]>([
    { provider: 'openrouter', label: 'OpenRouter API Key', value: '', status: 'untested' },
    { provider: 'openai', label: 'OpenAI API Key', value: '', status: 'untested' },
  ]);
  const { addToast } = useToast();

  const handleTest = async (index: number) => {
    const key = keys[index];
    if (!key.value.trim()) {
      addToast('Please enter an API key first', 'error');
      return;
    }

    setKeys((prev) =>
      prev.map((k, i) => (i === index ? { ...k, status: 'testing' } : k))
    );

    try {
      const resp = await fetch('/api/settings/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: key.provider, api_key: key.value }),
      });
      const data = await resp.json();
      setKeys((prev) =>
        prev.map((k, i) => (i === index ? { ...k, status: data.ok ? 'valid' : 'invalid' } : k))
      );
      if (data.ok) {
        addToast(`${key.label} is valid`, 'success');
      } else {
        addToast(`${key.label} failed: ${data.error}`, 'error');
      }
    } catch {
      setKeys((prev) =>
        prev.map((k, i) => (i === index ? { ...k, status: 'invalid' } : k))
      );
      addToast('Network error', 'error');
    }
  };

  return (
    <div>
      <h2 style={styles.heading}>API Keys</h2>
      <p style={styles.description}>
        Enter your API key, test it, and save. The key is stored in <code>.env</code> on your machine
        and persists across restarts. No data leaves your machine except API calls to the provider.
      </p>

      <div style={styles.cards}>
        {keys.map((key, i) => (
          <div key={key.provider} style={styles.card}>
            <div style={styles.cardHeader}>
              <span style={styles.label}>{key.label}</span>
              <StatusIndicator status={key.status} />
            </div>
            <div style={styles.inputRow}>
              <input
                type="password"
                style={styles.input}
                placeholder={`Enter ${key.provider} API key...`}
                value={key.value}
                onChange={(e) =>
                  setKeys((prev) =>
                    prev.map((k, j) => (j === i ? { ...k, value: e.target.value, status: 'untested' } : k))
                  )
                }
              />
              <button
                style={styles.testBtn}
                onClick={() => handleTest(i)}
                disabled={key.status === 'testing'}
              >
                {key.status === 'testing' ? 'Testing...' : 'Test'}
              </button>
              <button
                style={{
                  ...styles.testBtn,
                  background: key.status === 'valid' ? 'var(--brand-primary)' : 'var(--bg-primary)',
                  color: key.status === 'valid' ? 'white' : 'var(--text-primary)',
                }}
                onClick={async () => {
                  if (!key.value.trim()) return;
                  try {
                    const resp = await fetch('/api/settings/save-api-key', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ provider: key.provider, api_key: key.value }),
                    });
                    const data = await resp.json();
                    if (data.ok) addToast(`${key.label} saved to .env`, 'success');
                    else addToast(`Save failed: ${data.error}`, 'error');
                  } catch { addToast('Network error', 'error'); }
                }}
                disabled={!key.value.trim()}
              >
                Save
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusIndicator({ status }: { status: string }) {
  const colors: Record<string, string> = {
    untested: 'var(--text-muted)',
    testing: 'var(--color-warning)',
    valid: 'var(--color-success)',
    invalid: 'var(--color-error)',
  };
  const labels: Record<string, string> = {
    untested: 'Not tested',
    testing: 'Testing...',
    valid: 'Valid',
    invalid: 'Invalid',
  };

  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: colors[status] }}>
      <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: colors[status] }} />
      {labels[status]}
    </span>
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
  cards: {
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  card: {
    padding: '16px',
    background: 'var(--bg-primary)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-light)',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '10px',
  },
  label: {
    fontSize: '13px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  inputRow: {
    display: 'flex',
    gap: '8px',
  },
  input: {
    flex: 1,
    padding: '8px 12px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-medium)',
    background: 'var(--bg-secondary)',
    fontSize: '13px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-primary)',
    outline: 'none',
  },
  testBtn: {
    padding: '8px 16px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-medium)',
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: '12px',
    fontWeight: 600,
    fontFamily: 'var(--font-sans)',
    cursor: 'pointer',
    flexShrink: 0,
    transition: 'background 0.15s',
  },
};
