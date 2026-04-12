import { useCallback, useEffect, useRef, useState } from 'react';
import type { WsMessage } from '../types';

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

interface UseWebSocketReturn {
  status: ConnectionStatus;
  send: (message: WsMessage) => void;
  lastMessage: WsMessage | null;
  disconnect: () => void;
}

export function useWebSocket(url: string): UseWebSocketReturn {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout>>(undefined);
  // Guard: prevents the onclose auto-reconnect from firing after the
  // useEffect cleanup runs. Without this, React StrictMode (which
  // unmounts + remounts to surface side effects) causes a cascade:
  // cleanup closes WS1 → onclose schedules reconnect → reconnect
  // opens WS3 alongside WS2 (from second mount). The backend then
  // tries to send on the already-closed WS1 and crashes.
  const activeRef = useRef(true);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    const ws = new WebSocket(url);

    ws.onopen = () => {
      if (activeRef.current) setStatus('connected');
    };

    ws.onmessage = (event) => {
      if (!activeRef.current) return;
      try {
        const data = JSON.parse(event.data) as WsMessage;
        setLastMessage(data);
      } catch {
        setLastMessage({
          type: 'agent_message',
          payload: { content: event.data },
        });
      }
    };

    ws.onclose = () => {
      if (!activeRef.current) return;
      setStatus('disconnected');
      reconnectTimeout.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => ws.close();

    wsRef.current = ws;
  }, [url]);

  useEffect(() => {
    activeRef.current = true;
    connect();
    return () => {
      activeRef.current = false;
      clearTimeout(reconnectTimeout.current);
      const ws = wsRef.current;
      if (ws) {
        if (ws.readyState === WebSocket.CONNECTING) {
          // Let the handshake finish, then close gracefully.
          // Closing during CONNECTING causes the browser warning
          // "WebSocket is closed before the connection is established."
          ws.onopen = () => ws.close();
        } else {
          ws.close();
        }
      }
    };
  }, [connect]);

  const send = useCallback((message: WsMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimeout.current);
    wsRef.current?.close();
    wsRef.current = null;
    setStatus('disconnected');
    // Reconnect after a short delay
    reconnectTimeout.current = setTimeout(connect, 1000);
  }, [connect]);

  return { status, send, lastMessage, disconnect };
}
