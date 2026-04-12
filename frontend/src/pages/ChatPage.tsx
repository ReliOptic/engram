import { useCallback, useEffect, useState } from 'react';
import { ResizableLayout } from '../components/ResizableLayout';
import { Header } from '../components/Header';
import { AgentPanel } from '../components/AgentPanel';
import { ChatTimeline } from '../components/ChatTimeline';
import { ChatInput } from '../components/ChatInput';
import { SourceSidebar } from '../components/SourceSidebar';
import { KnowledgeStats } from '../components/KnowledgeStats';
import { HistorySidebar } from '../components/HistorySidebar';
import { useWebSocket } from '../hooks/useWebSocket';
import { useSessions } from '../hooks/useSessions';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import type { AgentMessage, AgentRole, AgentStatus, SiloSelection, SourceRef } from '../types';


export function ChatPage() {
  const wsUrl = `ws://${window.location.hostname}:8000/ws`;
  const { status: wsStatus, send, lastMessage, disconnect } = useWebSocket(wsUrl);

  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({
    analyzer: 'idle',
    finder: 'idle',
    reviewer: 'idle',
  });
  const [sources, setSources] = useState<SourceRef[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  // Sync status for header badge
  const [syncStatus, setSyncStatus] = useState<'disabled' | 'synced' | 'pending' | 'offline'>('disabled');
  const [syncPending, setSyncPending] = useState(0);
  useEffect(() => {
    fetch('/api/sync/status')
      .then(r => r.json())
      .then(data => {
        setSyncStatus(data.status || 'disabled');
        setSyncPending(data.pending_events || 0);
      })
      .catch(() => {});
    const interval = setInterval(() => {
      fetch('/api/sync/status')
        .then(r => r.json())
        .then(data => {
          setSyncStatus(data.status || 'disabled');
          setSyncPending(data.pending_events || 0);
        })
        .catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const {
    sessions,
    fetchSessions,
    deleteSession,
    renameSession,
  } = useSessions();

  // Handle incoming WebSocket messages
  useEffect(() => {
    if (!lastMessage) return;

    const { type, payload } = lastMessage;

    if (type === 'agent_message' && payload && typeof payload === 'object') {
      const p = payload as Record<string, unknown>;
      const agentMsg: AgentMessage = {
        id: (p.id as string) || `msg-${Date.now()}`,
        agent: (p.agent as AgentRole) || 'analyzer',
        contributionType: (p.contributionType as string) || '',
        content: (p.content as string) || '',
        addressedTo: p.addressedTo as string | undefined,
        timestamp: (p.timestamp as string) || new Date().toISOString(),
      };
      setMessages((prev) => [...prev, agentMsg]);

      // Extract sources from agent payload if available
      if (Array.isArray(p.sources)) {
        setSources((prev) => {
          const existing = new Set(prev.map((s) => s.id));
          const newSources = (p.sources as SourceRef[]).filter((s) => !existing.has(s.id));
          return newSources.length > 0 ? [...prev, ...newSources] : prev;
        });
      }
    }

    if (type === 'status_update' && payload && typeof payload === 'object') {
      const p = payload as Record<string, unknown>;

      // Capture session_id from backend
      if (p.session_id && typeof p.session_id === 'string' && !currentSessionId) {
        setCurrentSessionId(p.session_id as string);
        fetchSessions();
      }

      if (p.agent && p.status) {
        setAgentStatuses((prev) => ({
          ...prev,
          [p.agent as string]: p.status as AgentStatus,
        }));
      }
      if (p.status === 'complete') {
        setAgentStatuses({ analyzer: 'done', finder: 'done', reviewer: 'done' });
        setIsProcessing(false);
      }
    }

    if (type === 'error' && payload && typeof payload === 'object') {
      const p = payload as Record<string, unknown>;
      const errMsg: AgentMessage = {
        id: `err-${Date.now()}`,
        agent: 'analyzer',
        contributionType: '',
        content: `Error: ${p.message || 'Unknown error'}`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
      setIsProcessing(false);
    }
  }, [lastMessage, currentSessionId, fetchSessions]);

  const handleSend = useCallback(
    (text: string, silo: SiloSelection) => {
      const userMsg: AgentMessage = {
        id: `user-${Date.now()}`,
        agent: 'user',
        contributionType: '',
        content: text,
        silo: silo,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);

      // Reset agent statuses and start processing
      setAgentStatuses({ analyzer: 'idle', finder: 'idle', reviewer: 'idle' });
      setIsProcessing(true);

      // Send to backend via WebSocket with session_id
      send({
        type: 'user_message',
        payload: { text, silo, session_id: currentSessionId || '' },
      });
    },
    [send, currentSessionId],
  );

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setAgentStatuses({ analyzer: 'idle', finder: 'idle', reviewer: 'idle' });
    setSources([]);
    setIsProcessing(false);
    setCurrentSessionId(null);
  }, []);

  const handleSelectSession = useCallback(async (sessionId: string) => {
    try {
      const resp = await fetch(`/api/sessions/${sessionId}`);
      if (!resp.ok) return;
      const data = await resp.json();
      setCurrentSessionId(sessionId);
      const loaded: AgentMessage[] = (data.messages || []).map((m: Record<string, string>) => ({
        id: `loaded-${m.id}`,
        agent: (m.agent as AgentRole) || 'user',
        contributionType: m.contribution_type || '',
        content: m.content || '',
        addressedTo: m.addressed_to || undefined,
        timestamp: m.timestamp || '',
      }));
      setMessages(loaded);
      setSources([]);
      setIsProcessing(false);
      setAgentStatuses({ analyzer: 'idle', finder: 'idle', reviewer: 'idle' });
    } catch {
      // ignore
    }
  }, []);

  const handleStop = useCallback(() => {
    disconnect();
    setIsProcessing(false);
    setAgentStatuses({ analyzer: 'idle', finder: 'idle', reviewer: 'idle' });
  }, [disconnect]);

  const handleDeleteSession = useCallback(async (sessionId: string) => {
    await deleteSession(sessionId);
    if (currentSessionId === sessionId) {
      handleNewChat();
    }
  }, [deleteSession, currentSessionId, handleNewChat]);

  const handleRenameSession = useCallback(async (sessionId: string, title: string) => {
    await renameSession(sessionId, title);
  }, [renameSession]);

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onNewChat: handleNewChat,
    onFocusInput: () => {
      const input = document.querySelector<HTMLElement>(
        'textarea[placeholder*="Describe"], input[placeholder*="Describe"]'
      );
      input?.focus();
    },
    onToggleLeftSidebar: () => {
      window.dispatchEvent(new CustomEvent('engram-toggle-left-sidebar'));
    },
    onStop: isProcessing ? handleStop : undefined,
  });

  return (
    <ResizableLayout
      header={<Header wsStatus={wsStatus} syncStatus={syncStatus} syncPending={syncPending} />}
      leftTop={<AgentPanel agentStatuses={agentStatuses} />}
      leftBottom={
        <HistorySidebar
          sessions={sessions}
          currentSessionId={currentSessionId}
          onNewChat={handleNewChat}
          onSelect={handleSelectSession}
          onDelete={handleDeleteSession}
          onRename={handleRenameSession}
        />
      }
      center={
        <>
          <ChatTimeline messages={messages} isProcessing={isProcessing} />
          <ChatInput onSend={handleSend} disabled={isProcessing} isProcessing={isProcessing} onStop={handleStop} />
        </>
      }
      right={
        <>
          <KnowledgeStats />
          <SourceSidebar sources={sources} />
        </>
      }
    />
  );
}
