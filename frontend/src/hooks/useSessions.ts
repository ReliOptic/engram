import { useCallback, useEffect, useState } from 'react';

export interface Session {
  session_id: string;
  title: string;
  silo_account: string;
  silo_tool: string;
  silo_component: string;
  status: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch('/api/sessions?status=active');
      if (resp.ok) {
        const data: Session[] = await resp.json();
        setSessions(data);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  const createSession = useCallback(async (title: string, silo?: { account: string; tool: string; component: string }) => {
    const resp = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        silo_account: silo?.account || '',
        silo_tool: silo?.tool || '',
        silo_component: silo?.component || '',
      }),
    });
    if (resp.ok) {
      const session: Session = await resp.json();
      setSessions((prev) => [session, ...prev]);
      return session;
    }
    return null;
  }, []);

  const deleteSession = useCallback(async (sessionId: string) => {
    const resp = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
    if (resp.ok) {
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    }
  }, []);

  const renameSession = useCallback(async (sessionId: string, title: string) => {
    const resp = await fetch(`/api/sessions/${sessionId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (resp.ok) {
      setSessions((prev) =>
        prev.map((s) => (s.session_id === sessionId ? { ...s, title } : s))
      );
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  return { sessions, loading, fetchSessions, createSession, deleteSession, renameSession };
}
