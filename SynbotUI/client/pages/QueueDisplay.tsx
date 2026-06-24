import { useState, useEffect, useCallback } from "react";
import { useRealtimeChannel } from "@/hooks/use-realtime-channel";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

interface QueueEntry {
  queue_number: string;
  room?: string;
}

interface DisplayData {
  called: QueueEntry[];
  now_serving: QueueEntry[];
  waiting_next: QueueEntry[];
  as_of: string;
}

function useClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

export default function QueueDisplay() {
  const now = useClock();
  const [data, setData] = useState<DisplayData>({
    called: [], now_serving: [], waiting_next: [], as_of: "",
  });
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const loadDisplay = useCallback(async () => {
    try {
      const res = await api.hospital.display.getQueue();
      if (res) {
        setData(res);
        setLastUpdate(new Date());
      }
    } catch {
      // silent fail — polling will retry
    }
  }, []);

  // Initial load + 10-second polling fallback
  useEffect(() => {
    void loadDisplay();
    const t = setInterval(() => void loadDisplay(), 10_000);
    return () => clearInterval(t);
  }, [loadDisplay]);

  // Live WS updates
  useRealtimeChannel("encounter_updates", () => {
    void loadDisplay();
  });

  return (
    <div className="min-h-screen bg-slate-950 text-white flex flex-col select-none">
      {/* Header bar */}
      <header className="border-b border-slate-800 px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center">
            <span className="text-primary font-bold text-lg">R</span>
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-wide">RoyanHealth</h1>
            <p className="text-xs text-slate-400">Patient Queue Board</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-2xl font-mono font-bold text-slate-100">
            {now.toLocaleTimeString("en-NG", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </p>
          <p className="text-xs text-slate-400">
            {now.toLocaleDateString("en-NG", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
          </p>
        </div>
      </header>

      {/* Main board */}
      <main className="flex-1 grid grid-cols-3 gap-0 divide-x divide-slate-800 p-6 gap-6">

        {/* Now Serving */}
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-3 mb-2">
            <span className="h-3 w-3 rounded-full bg-green-500 animate-pulse" />
            <h2 className="text-sm font-semibold uppercase tracking-widest text-green-400">
              Now Being Served
            </h2>
          </div>
          <div className="space-y-3">
            {data.now_serving.length === 0 ? (
              <EmptySlot label="No active consultations" />
            ) : data.now_serving.map((e, i) => (
              <TicketCard key={e.queue_number + i} entry={e} variant="serving" highlight={i === 0} />
            ))}
          </div>
        </section>

        {/* Called — center, highlighted */}
        <section className="flex flex-col gap-4 px-6">
          <div className="flex items-center gap-3 mb-2">
            <span className="h-3 w-3 rounded-full bg-blue-400 animate-pulse" />
            <h2 className="text-sm font-semibold uppercase tracking-widest text-blue-400">
              Called — Please Proceed
            </h2>
          </div>
          <div className="space-y-3">
            {data.called.length === 0 ? (
              <EmptySlot label="No patients called" />
            ) : data.called.map((e, i) => (
              <TicketCard key={e.queue_number + i} entry={e} variant="called" highlight={i === 0} />
            ))}
          </div>
        </section>

        {/* Waiting Next */}
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-3 mb-2">
            <span className="h-3 w-3 rounded-full bg-slate-400" />
            <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
              Waiting — Next Up
            </h2>
          </div>
          <div className="space-y-2">
            {data.waiting_next.length === 0 ? (
              <EmptySlot label="Queue is clear" />
            ) : data.waiting_next.map((e, i) => (
              <WaitingCard key={e.queue_number + i} entry={e} position={i + 1} />
            ))}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 px-8 py-2 flex items-center justify-between text-xs text-slate-500">
        <span>Please listen for your ticket number to be announced.</span>
        <span>
          {lastUpdate
            ? `Updated ${lastUpdate.toLocaleTimeString("en-NG", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
            : "Connecting…"}
        </span>
      </footer>
    </div>
  );
}

function TicketCard({
  entry, variant, highlight,
}: { entry: QueueEntry; variant: "called" | "serving"; highlight: boolean }) {
  const colors = {
    called:  {
      border: highlight ? "border-blue-400 ring-2 ring-blue-400/40" : "border-blue-800",
      bg: "bg-blue-950/40",
      num: "text-blue-300",
      dot: "bg-blue-400",
    },
    serving: {
      border: highlight ? "border-green-400 ring-2 ring-green-400/40" : "border-green-900",
      bg: "bg-green-950/30",
      num: "text-green-300",
      dot: "bg-green-500",
    },
  }[variant];

  return (
    <div className={cn("rounded-xl border p-5 flex items-center justify-between", colors.bg, colors.border)}>
      <div>
        <p className={cn("text-4xl font-bold font-mono tracking-widest", colors.num)}>
          {entry.queue_number}
        </p>
        {entry.room && (
          <p className="text-sm text-slate-400 mt-1">{entry.room}</p>
        )}
      </div>
      <span className={cn("h-4 w-4 rounded-full", colors.dot, highlight && "animate-pulse")} />
    </div>
  );
}

function WaitingCard({ entry, position }: { entry: QueueEntry; position: number }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3 flex items-center gap-4">
      <span className="text-slate-600 text-sm font-mono w-5">{position}.</span>
      <span className="text-xl font-bold font-mono text-slate-300">{entry.queue_number}</span>
    </div>
  );
}

function EmptySlot({ label }: { label: string }) {
  return (
    <div className="rounded-xl border border-slate-800 border-dashed p-8 text-center text-slate-600 text-sm">
      {label}
    </div>
  );
}
