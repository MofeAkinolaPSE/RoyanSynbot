import { useRealtimeChannel } from "@/hooks/use-realtime-channel";

const HEARTBEAT_MS = 30_000;

// Opens (and keeps open across every route change) the app-wide "presence"
// WebSocket channel so this session counts toward "who's online" — mounted
// once at AuthProvider (session lifetime), not inside any one dashboard page
// (which would die the moment the user navigates away, per staff_updates'
// existing page-lifetime behavior).
export function usePresenceHeartbeat(enabled: boolean) {
  useRealtimeChannel("presence", () => {}, enabled, { heartbeatMs: HEARTBEAT_MS });
}
