import { useEffect, useRef, useState, useCallback } from 'react';

export interface WsMessage {
  type: string;
  stage?: string;
  status?: string;
  message?: string;
  timestamp?: string;
  [key: string]: unknown;
}

interface UseWebSocketReturn {
  messages: WsMessage[];
  isConnected: boolean;
  lastEvent: WsMessage | null;
}

const MAX_RETRIES = 5;
const BASE_DELAY_MS = 1000;

/**
 * Custom hook that maintains a WebSocket connection to the pipeline run stream.
 *
 * Connects to `ws://<host>/ws/pipeline/{runId}`.  Automatically reconnects on
 * unexpected disconnects (up to {@link MAX_RETRIES} attempts with exponential
 * back-off).  Cleans up the socket when the component unmounts or `runId`
 * changes.
 */
export function useWebSocket(runId: string | null): UseWebSocketReturn {
  const [messages, setMessages] = useState<WsMessage[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WsMessage | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track whether the hook is still mounted so we don't set state after cleanup.
  const mountedRef = useRef(true);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const connect = useCallback(
    (id: string) => {
      // Determine the ws protocol based on the page protocol.
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${protocol}//${window.location.host}/ws/pipeline/${id}`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setIsConnected(true);
        retriesRef.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return;
        try {
          const parsed: WsMessage = JSON.parse(event.data);
          setMessages((prev) => [...prev, parsed]);
          setLastEvent(parsed);
        } catch {
          // Non-JSON payload — wrap it in a generic message.
          const fallback: WsMessage = { type: 'raw', message: String(event.data) };
          setMessages((prev) => [...prev, fallback]);
          setLastEvent(fallback);
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setIsConnected(false);

        // Attempt reconnection with exponential back-off.
        if (retriesRef.current < MAX_RETRIES) {
          const delay = BASE_DELAY_MS * Math.pow(2, retriesRef.current);
          retriesRef.current += 1;
          reconnectTimerRef.current = setTimeout(() => {
            if (mountedRef.current) {
              connect(id);
            }
          }, delay);
        }
      };

      ws.onerror = () => {
        // The browser fires `onclose` after `onerror`, so reconnection is
        // handled there.  We just ensure the socket is closed cleanly.
        ws.close();
      };
    },
    [],
  );

  useEffect(() => {
    mountedRef.current = true;

    // Reset state when runId changes.
    setMessages([]);
    setLastEvent(null);
    setIsConnected(false);
    retriesRef.current = 0;
    clearReconnectTimer();

    if (runId) {
      connect(runId);
    }

    return () => {
      mountedRef.current = false;
      clearReconnectTimer();
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [runId, connect, clearReconnectTimer]);

  return { messages, isConnected, lastEvent };
}
