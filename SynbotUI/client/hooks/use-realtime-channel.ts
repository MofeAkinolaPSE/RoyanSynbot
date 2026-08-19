import { useEffect, useRef } from "react";
import { authClient } from "@/lib/auth-client";
import { API_BASE_URL } from "@/lib/api-base";
import { api } from "@/lib/api-client";

type MessageHandler = (message: any) => void;

function buildWsUrl(path: string, ticket: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (API_BASE_URL) {
    const withTicket = `${API_BASE_URL}${normalized}?ticket=${encodeURIComponent(ticket)}`;
    if (withTicket.startsWith("https://")) return withTicket.replace("https://", "wss://");
    if (withTicket.startsWith("http://")) return withTicket.replace("http://", "ws://");
    return withTicket;
  }
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const withTicket = `${origin}${normalized}?ticket=${encodeURIComponent(ticket)}`;
  if (withTicket.startsWith("https://")) return withTicket.replace("https://", "wss://");
  return withTicket.replace("http://", "ws://");
}

export function useRealtimeChannel(channel: string, onMessage: MessageHandler, enabled: boolean = true, options?: { heartbeatMs?: number }) {
  const onMessageRef = useRef<MessageHandler>(onMessage);
  const retriesRef = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);
  const heartbeatMs = options?.heartbeatMs;

  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!enabled) return;

    let stopped = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null;

    const connect = async () => {
      const token = authClient.getAccessToken();
      if (!token) return;

      try {
        const { ticket } = await api.realtime.getWsTicket();
        if (stopped) return;
        const ws = new WebSocket(buildWsUrl(`/realtime/ws/${channel}`, ticket));
        socketRef.current = ws;

        ws.onopen = () => {
          retriesRef.current = 0;
          if (heartbeatMs) {
            heartbeatTimer = setInterval(() => {
              if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
            }, heartbeatMs);
          }
        };

        ws.onmessage = (evt) => {
          try {
            const payload = JSON.parse(evt.data);
            onMessageRef.current(payload);
          } catch {
            // Ignore malformed frames
          }
        };

        ws.onclose = async () => {
          if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
          if (stopped) return;
          if (!authClient.getAccessToken()) {
            const refreshed = await authClient.refresh();
            if (!refreshed) return;
          }
          const attempt = Math.min(retriesRef.current + 1, 6);
          retriesRef.current = attempt;
          const backoff = Math.min(1000 * 2 ** attempt, 15000);
          reconnectTimer = setTimeout(() => {
            void connect();
          }, backoff);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch {
        const attempt = Math.min(retriesRef.current + 1, 6);
        retriesRef.current = attempt;
        const backoff = Math.min(1000 * 2 ** attempt, 15000);
        reconnectTimer = setTimeout(() => {
          void connect();
        }, backoff);
      }
    };

    void connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (heartbeatTimer) clearInterval(heartbeatTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [channel, enabled, heartbeatMs]);
}
