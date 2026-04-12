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

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    const ws = new WebSocket(url);

    ws.onopen = () => setStatus('connected');

    ws.onmessage = (event) => {
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
      setStatus('disconnected');
      reconnectTimeout.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => ws.close();

    wsRef.current = ws;
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimeout.current);
      wsRef.current?.close();
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
