import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ModelSettings } from '../components/settings/ModelSettings';
import { APIKeySettings } from '../components/settings/APIKeySettings';
import { VectorDBSettings } from '../components/settings/VectorDBSettings';
import { DropdownSettings } from '../components/settings/DropdownSettings';
import { SyncSettings } from '../components/settings/SyncSettings';
import { CostSettings } from '../components/settings/CostSettings';

type SettingsTab = 'models' | 'apikeys' | 'vectordb' | 'dropdowns' | 'sync' | 'costs';

const TABS: { id: SettingsTab; label: string }[] = [
  { id: 'models', label: 'Models' },
  { id: 'apikeys', label: 'API Keys' },
  { id: 'vectordb', label: 'VectorDB' },
  { id: 'dropdowns', label: 'Dropdowns' },
  { id: 'sync', label: 'Sync' },
  { id: 'costs', label: 'Costs' },
];

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('models');

  return (
    <div style={styles.root}>
      <header style={styles.header}>
        <Link to="/" style={styles.backLink}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ marginRight: 6 }}>
            <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Back to Chat
        </Link>
        <h1 style={styles.title}>Settings</h1>
      </header>

      <div style={styles.body}>
        <nav style={styles.tabBar}>
          {TABS.map((tab) => (
            <button
              key={tab.id}
              style={{
                ...styles.tab,
                ...(activeTab === tab.id ? styles.tabActive : {}),
              }}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div style={styles.content}>
          {activeTab === 'models' && <ModelSettings />}
          {activeTab === 'apikeys' && <APIKeySettings />}
          {activeTab === 'vectordb' && <VectorDBSettings />}
          {activeTab === 'dropdowns' && <DropdownSettings />}
          {activeTab === 'sync' && <SyncSettings />}
          {activeTab === 'costs' && <CostSettings />}
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--bg-secondary)',
  },
  header: {
    height: 'var(--header-height)',
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    padding: '0 24px',
    background: 'var(--brand-primary)',
    color: 'var(--text-on-dark)',
    flexShrink: 0,
  },
  backLink: {
    display: 'flex',
    alignItems: 'center',
    color: 'rgba(255,255,255,0.8)',
    textDecoration: 'none',
    fontSize: '13px',
    fontWeight: 500,
    fontFamily: 'var(--font-family)',
    padding: '4px 8px',
    borderRadius: 'var(--radius-sm)',
    transition: 'background 0.15s, color 0.15s',
  },
  title: {
    fontSize: '16px',
    fontWeight: 600,
    margin: 0,
  },
  body: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    maxWidth: '900px',
    width: '100%',
    margin: '0 auto',
    padding: '24px',
    overflow: 'auto',
  },
  tabBar: {
    display: 'flex',
    gap: '4px',
    borderBottom: '1px solid var(--border-light)',
    marginBottom: '24px',
    flexShrink: 0,
  },
  tab: {
    padding: '8px 16px',
    fontSize: '13px',
    fontWeight: 500,
    fontFamily: 'var(--font-family)',
    color: 'var(--text-secondary)',
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    cursor: 'pointer',
    transition: 'color 0.15s, border-color 0.15s',
  },
  tabActive: {
    color: 'var(--brand-primary)',
    borderBottomColor: 'var(--brand-primary)',
    fontWeight: 600,
  },
  content: {
    flex: 1,
  },
};
