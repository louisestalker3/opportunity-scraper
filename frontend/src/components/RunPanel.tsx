import { useState } from "react";
import { ExternalLink, Play, Square, Loader2, Globe, Server, Database, Zap } from "lucide-react";
import { useProjectServices, useServiceLogs } from "@/hooks/useOpportunities";
import { useRef, useEffect } from "react";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function svcIcon(name: string) {
  const n = name.toLowerCase();
  if (n.includes("front") || n.includes("web") || n.includes("next") || n.includes("nginx")) return Globe;
  if (n.includes("postgres") || n.includes("mysql") || n.includes("db")) return Database;
  return Server;
}

function logLineClass(line: string): string {
  const l = line.toLowerCase();
  if (/error|fatal|panic|exception|fail/.test(l)) return "text-red-400";
  if (/warn/.test(l)) return "text-yellow-300";
  if (/ready|started|listening|success|✅/.test(l)) return "text-emerald-400";
  return "text-gray-300";
}

function useAutoScroll(dep: unknown) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [dep]);
  return ref;
}

// ─── Service log console ──────────────────────────────────────────────────────

function ServiceConsole({ itemId, service, active }: { itemId: string; service: string; active: boolean }) {
  const { data, isLoading } = useServiceLogs(itemId, service, active);
  const ref = useAutoScroll(data?.lines);

  return (
    <div ref={ref} className="bg-gray-950 font-mono text-xs leading-5 px-4 py-3 h-72 overflow-y-auto">
      {isLoading && <p className="text-gray-600 animate-pulse">Fetching logs...</p>}
      {!isLoading && !data?.lines?.length && (
        <p className="text-gray-600">No log output yet.</p>
      )}
      {data?.lines?.map((line, i) => (
        <div key={i} className={logLineClass(line)}>
          <span className="select-none text-gray-700 mr-3">{String(i + 1).padStart(4, " ")}</span>
          {line}
        </div>
      ))}
    </div>
  );
}

// ─── Run panel ────────────────────────────────────────────────────────────────

export default function RunPanel({
  itemId,
  runStatus,
  runUrl,
  onStart,
  onStop,
  onForceStop,
  startPending,
  stopPending,
  forceStopPending,
}: {
  itemId: string;
  runStatus: string | null;
  runUrl: string | null;
  onStart: () => void;
  onStop: () => void;
  onForceStop: () => void;
  startPending: boolean;
  stopPending: boolean;
  forceStopPending: boolean;
}) {
  const isRunning = runStatus === "running";
  const isTransitioning = runStatus === "starting" || runStatus === "stopping";
  const isActive = isRunning || isTransitioning;

  const { data: servicesData } = useProjectServices(itemId, true);
  const services = servicesData?.services ?? [];

  const [activeTab, setActiveTab] = useState<string>("");
  const currentTab = activeTab || services[0]?.name || "";
  const currentService = services.find((s) => s.name === currentTab);

  return (
    <div className="border border-gray-200 rounded-2xl overflow-hidden bg-white">
      {/* Header */}
      <div className={`flex items-center gap-3 px-5 py-3 border-b border-gray-100 ${isRunning ? "bg-emerald-50" : "bg-gray-50"}`}>
        <span className={`w-2 h-2 rounded-full shrink-0 ${isRunning ? "bg-emerald-500 animate-pulse" : isTransitioning ? "bg-yellow-400 animate-pulse" : "bg-gray-300"}`} />
        <span className="text-sm font-semibold text-gray-800">
          {isRunning ? "Running" : runStatus === "starting" ? "Starting…" : runStatus === "stopping" ? "Stopping…" : "Stopped"}
        </span>
        {isTransitioning && <Loader2 size={13} className="animate-spin text-gray-400" />}
        {isRunning && runUrl && (
          <a href={runUrl} target="_blank" rel="noopener noreferrer"
            className="ml-1 text-xs text-emerald-600 hover:underline flex items-center gap-1">
            {runUrl} <ExternalLink size={10} />
          </a>
        )}
        <div className="ml-auto flex items-center gap-2">
          {isRunning || isTransitioning ? (
            <>
              <button
                onClick={onStop}
                disabled={stopPending || runStatus === "stopping"}
                className="flex items-center gap-1.5 text-xs font-medium bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-40"
              >
                <Square size={11} /> Stop
              </button>
              <button
                onClick={onForceStop}
                disabled={forceStopPending}
                className="flex items-center gap-1.5 text-xs font-medium bg-red-50 border border-red-200 text-red-600 hover:bg-red-100 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-40"
                title="Kill all processes immediately (SIGKILL)"
              >
                <Zap size={11} /> Force Stop
              </button>
            </>
          ) : (
            <button
              onClick={onStart}
              disabled={startPending}
              className="flex items-center gap-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
            >
              <Play size={11} /> Start App
            </button>
          )}
        </div>
      </div>

      {/* Service tabs */}
      {services.length > 0 ? (
        <>
          <div className="flex border-b border-gray-100 bg-gray-50 overflow-x-auto">
            {services.map((svc) => {
              const Icon = svcIcon(svc.name);
              const isTab = currentTab === svc.name;
              return (
                <button
                  key={svc.name}
                  onClick={() => setActiveTab(svc.name)}
                  className={[
                    "flex items-center gap-2 px-4 py-2.5 text-xs font-medium whitespace-nowrap border-b-2 transition-colors",
                    isTab
                      ? "border-emerald-500 text-emerald-700 bg-white"
                      : "border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-100",
                  ].join(" ")}
                >
                  <Icon size={12} />
                  {svc.name}
                  {svc.ports.length > 0 && (
                    <span className="text-gray-400 font-mono">
                      :{svc.ports.map((p) => p.host).join(", :")}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Port strip */}
          {currentService && currentService.ports.length > 0 && (
            <div className="flex items-center gap-4 px-4 py-2 bg-gray-950 border-b border-gray-800">
              {currentService.ports.map((p) => (
                <div key={p.host}>
                  {isRunning ? (
                    <a
                      href={`http://localhost:${p.host}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs font-mono text-emerald-400 hover:underline flex items-center gap-1"
                    >
                      localhost:{p.host} <ExternalLink size={9} />
                    </a>
                  ) : (
                    <span className="text-xs font-mono text-gray-500">localhost:{p.host}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {currentTab && (
            <ServiceConsole itemId={itemId} service={currentTab} active={isActive} />
          )}
        </>
      ) : (
        <div className="px-5 py-6 text-xs text-gray-400 text-center">Loading services…</div>
      )}
    </div>
  );
}
