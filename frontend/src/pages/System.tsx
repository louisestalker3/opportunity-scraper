import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

interface RunnerInfo {
  runner: string;
  alive: boolean;
  last_seen: number | null;
  last_seen_ago: number | null;
}

interface LogEntry {
  ts: number;
  line: string;
}

const RUNNER_LABELS: Record<string, string> = {
  build_runner: "Builder",
  celery: "Scraper",
};

const RUNNER_COLORS: Record<string, string> = {
  build_runner: "blue",
  celery: "purple",
};

function StatusBadge({ alive, ago }: { alive: boolean; ago: number | null }) {
  if (ago === null) return <span className="text-xs text-gray-400">never connected</span>;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${alive ? "text-green-700" : "text-red-600"}`}>
      <span className={`w-2 h-2 rounded-full ${alive ? "bg-green-400 shadow-[0_0_5px_rgba(74,222,128,0.7)]" : "bg-red-400"}`} />
      {alive ? `alive · ${ago}s ago` : `offline · ${Math.round(ago)}s ago`}
    </span>
  );
}

function LogPanel({ runner, alive }: { runner: string; alive: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const color = RUNNER_COLORS[runner] ?? "gray";

  const { data: logs } = useQuery<LogEntry[]>({
    queryKey: ["runner-logs", runner],
    queryFn: () => api.get(`/api/status/logs/${runner}?tail=300`).then((r) => r.data),
    refetchInterval: 2000,
    staleTime: 1000,
  });

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  };

  const colorClass: Record<string, string> = {
    blue: "border-blue-200 bg-blue-950",
    purple: "border-purple-200 bg-purple-950",
    gray: "border-gray-200 bg-gray-950",
  };

  return (
    <div
      onScroll={handleScroll}
      className={`h-96 overflow-y-auto rounded-lg border font-mono text-xs p-3 space-y-0.5 ${colorClass[color] ?? colorClass.gray}`}
    >
      {!logs || logs.length === 0 ? (
        <p className="text-gray-500 italic">
          {alive
            ? "Connected — runner is idle or logs are still syncing. Lines appear when a build/run starts or when the next heartbeat posts output."
            : "No output yet…"}
        </p>
      ) : (
        logs.map((entry, i) => (
          <LogLine key={i} entry={entry} />
        ))
      )}
      <div ref={bottomRef} />
    </div>
  );
}

function LogLine({ entry }: { entry: LogEntry }) {
  const time = new Date(entry.ts * 1000).toLocaleTimeString("en-AU", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });

  const line = entry.line;
  let textColor = "text-gray-300";
  if (/error|fail|❌/i.test(line)) textColor = "text-red-400";
  else if (/warn/i.test(line)) textColor = "text-yellow-400";
  else if (/✅|done|success|complete/i.test(line)) textColor = "text-green-400";
  else if (/🚀|🤖|🔧|starting|building|running/i.test(line)) textColor = "text-blue-300";

  return (
    <div className="flex gap-2 leading-5">
      <span className="text-gray-600 shrink-0 select-none">{time}</span>
      <span className={textColor}>{line}</span>
    </div>
  );
}

export default function System() {
  const queryClient = useQueryClient();
  const [activeRunner, setActiveRunner] = useState("build_runner");
  const [restarting, setRestarting] = useState<string | null>(null);
  const [confirmRunner, setConfirmRunner] = useState<string | null>(null);

  const { data: runners } = useQuery<RunnerInfo[]>({
    queryKey: ["runner-status"],
    queryFn: () => api.get("/api/status/runners").then((r) => r.data),
    refetchInterval: 5000,
    staleTime: 3000,
  });

  const restartMutation = useMutation({
    mutationFn: (runner: string) => api.post(`/api/status/restart/${runner}`),
    onMutate: (runner) => {
      setConfirmRunner(null);
      setRestarting(runner);
      // Immediately clear the cached log so the panel goes blank right away
      queryClient.setQueryData(["runner-logs", runner], []);
    },
    onSettled: () => setRestarting(null),
  });

  const knownRunners = ["build_runner", "celery"];

  return (
    <div className="space-y-6">
      {/* Confirm restart modal */}
      {confirmRunner && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl p-6 w-80 space-y-4">
            <h3 className="text-base font-semibold text-gray-900">
              Restart {RUNNER_LABELS[confirmRunner] ?? confirmRunner}?
            </h3>
            <p className="text-sm text-gray-500">
              The process will be killed and restarted. Any in-progress work will be interrupted.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmRunner(null)}
                className="px-4 py-2 text-sm rounded-lg border border-gray-200 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => restartMutation.mutate(confirmRunner)}
                className="px-4 py-2 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 font-medium"
              >
                Restart
              </button>
            </div>
          </div>
        </div>
      )}

      <div>
        <h1 className="text-2xl font-bold text-gray-900">System</h1>
        <p className="text-sm text-gray-500 mt-1">Live output from background runners</p>
      </div>

      {/* Runner status cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {knownRunners.map((name) => {
          const info = runners?.find((r) => r.runner === name);
          const label = RUNNER_LABELS[name] ?? name;
          const color = RUNNER_COLORS[name] ?? "gray";
          const borderActive = activeRunner === name ? "ring-2 ring-offset-1" : "";
          const ringColor: Record<string, string> = {
            blue: "ring-blue-400",
            purple: "ring-purple-400",
            gray: "ring-gray-400",
          };
          const isRestarting = restarting === name;

          return (
            <div
              key={name}
              onClick={() => setActiveRunner(name)}
              className={`cursor-pointer text-left p-4 rounded-lg border bg-white shadow-sm hover:shadow-md transition-shadow ${borderActive} ${ringColor[color] ?? ""}`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold text-gray-800">{label}</div>
              </div>
              <StatusBadge alive={info?.alive ?? false} ago={info?.last_seen_ago ?? null} />
              <button
                onClick={(e) => { e.stopPropagation(); setConfirmRunner(name); }}
                disabled={isRestarting}
                className="mt-3 w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-200 bg-gray-50 hover:bg-red-50 hover:border-red-300 hover:text-red-600 text-xs font-medium text-gray-600 transition-colors disabled:opacity-50"
              >
                {isRestarting ? (
                  <><span className="animate-spin">↺</span> Restarting…</>
                ) : (
                  <><span>↺</span> Restart</>
                )}
              </button>
            </div>
          );
        })}
      </div>

      {/* Log panel */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700">
            {RUNNER_LABELS[activeRunner] ?? activeRunner} — output
          </h2>
          <div className="flex gap-2">
            {knownRunners.map((name) => (
              <button
                key={name}
                onClick={() => setActiveRunner(name)}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                  activeRunner === name
                    ? "bg-gray-800 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {RUNNER_LABELS[name] ?? name}
              </button>
            ))}
          </div>
        </div>
        <LogPanel
          runner={activeRunner}
          alive={runners?.find((r) => r.runner === activeRunner)?.alive ?? false}
        />
      </div>
    </div>
  );
}
