import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

interface RunnerInfo {
  runner: string;
  alive: boolean;
  last_seen: number | null;
  last_seen_ago: number | null;
}

const LABELS: Record<string, string> = {
  build_runner: "Builder",
  celery: "Scraper",
};

function Dot({ alive, label, ago }: { alive: boolean; label: string; ago: number | null }) {
  const never = ago === null;
  const tooltip = never
    ? `${label}: never connected`
    : alive
    ? `${label}: alive (${ago}s ago)`
    : `${label}: offline (last seen ${Math.round(ago)}s ago)`;

  return (
    <div className="flex items-center gap-1.5 group relative" title={tooltip}>
      <span
        className={[
          "w-2 h-2 rounded-full transition-colors",
          never   ? "bg-gray-300" :
          alive   ? "bg-green-400 shadow-[0_0_4px_rgba(74,222,128,0.8)]" :
                    "bg-red-400",
        ].join(" ")}
      />
      <span className="text-xs text-gray-400 hidden sm:inline">{label}</span>
    </div>
  );
}

export default function RunnerStatus() {
  const { data } = useQuery<RunnerInfo[]>({
    queryKey: ["runner-status"],
    queryFn: () => api.get("/api/status/runners").then((r) => r.data),
    refetchInterval: 8000,
    staleTime: 5000,
  });

  if (!data) return null;

  return (
    <div className="flex items-center gap-3 px-3 py-1.5 rounded-lg bg-gray-50 border border-gray-200">
      {data.map((r) => (
        <Dot
          key={r.runner}
          alive={r.alive}
          label={LABELS[r.runner] ?? r.runner}
          ago={r.last_seen_ago}
        />
      ))}
    </div>
  );
}
