import { Link } from "react-router-dom";
import { ExternalLink, Play, Square, Loader2, GitBranch, TrendingUp, Boxes } from "lucide-react";
import {
  usePipeline,
  useStartProject,
  useStopProject,
  useForceStopProject,
  useOpportunities,
} from "@/hooks/useOpportunities";
import type { PipelineItem } from "@/api/client";

function RunBadge({ item, onStart, onStop }: {
  item: PipelineItem;
  onStart: () => void;
  onStop: () => void;
}) {
  const { run_status } = item;

  if (run_status === "running") {
    return (
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          Running
        </span>
        {item.run_url && (
          <a href={item.run_url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-emerald-600 hover:underline flex items-center gap-1">
            Open <ExternalLink size={10} />
          </a>
        )}
        <button onClick={onStop}
          className="ml-auto text-xs text-gray-400 hover:text-red-500 transition-colors">
          <Square size={13} />
        </button>
      </div>
    );
  }

  if (run_status === "starting" || run_status === "stopping") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-gray-500">
        <Loader2 size={11} className="animate-spin" />
        {run_status === "starting" ? "Starting…" : "Stopping…"}
      </span>
    );
  }

  return (
    <button onClick={onStart}
      className="flex items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-emerald-600 transition-colors">
      <Play size={11} /> Start
    </button>
  );
}

function ProjectCard({ item }: { item: PipelineItem }) {
  const startMutation = useStartProject();
  const stopMutation = useStopProject();
  const forceStop = useForceStopProject();
  const { data: oppsData } = useOpportunities({ page_size: 200 });
  const opp = oppsData?.items.find((o) => o.id === item.opportunity_id);

  let plan: Record<string, unknown> = {};
  try { plan = JSON.parse(item.app_plan ?? "{}"); } catch { /* ignore */ }

  const appName = (plan.app_name as string) || opp?.app_profile?.name || "Unnamed App";
  const tagline = plan.tagline as string | undefined;
  const scale = plan.scale as string | undefined;
  const stack = plan.tech_stack as Record<string, string> | undefined;

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5 flex flex-col gap-4 hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to={`/project/${item.id}`}
            className="text-base font-bold text-gray-900 hover:text-emerald-700 transition-colors truncate block">
            {appName}
          </Link>
          {tagline && <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{tagline}</p>}
        </div>
        {scale && (
          <span className={`shrink-0 text-xs font-medium rounded-full px-2.5 py-0.5 border ${
            scale === "small"
              ? "bg-blue-50 text-blue-600 border-blue-200"
              : "bg-purple-50 text-purple-600 border-purple-200"
          }`}>
            {scale}
          </span>
        )}
      </div>

      {/* Tech stack pills */}
      {stack && (
        <div className="flex flex-wrap gap-1.5">
          {["backend", "frontend", "database"].map((k) => stack[k] && (
            <span key={k} className="text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">
              {stack[k]}
            </span>
          ))}
        </div>
      )}

      {/* Run control */}
      <div className="border-t border-gray-100 pt-3">
        <RunBadge
          item={item}
          onStart={() => startMutation.mutate(item.id)}
          onStop={() => stopMutation.mutate(item.id)}
        />
      </div>

      {/* Footer links */}
      <div className="flex items-center gap-3 text-xs border-t border-gray-100 pt-3">
        <Link to={`/project/${item.id}`}
          className="flex items-center gap-1 text-emerald-600 hover:underline font-medium">
          <Boxes size={11} /> Project
        </Link>
        <Link to={`/opportunity/${item.opportunity_id}`}
          className="flex items-center gap-1 text-gray-400 hover:text-gray-700">
          <TrendingUp size={11} /> Opportunity
        </Link>
        {item.built_repo_url && (
          <a href={item.built_repo_url} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-gray-400 hover:text-gray-700 ml-auto">
            <GitBranch size={11} /> GitHub
          </a>
        )}
        {(item.run_status === "running" || item.run_status === "starting") && (
          <button onClick={() => forceStop.mutate(item.id)}
            disabled={forceStop.isPending}
            className="ml-auto text-xs text-red-400 hover:text-red-600 disabled:opacity-40">
            Force stop
          </button>
        )}
      </div>
    </div>
  );
}

export default function Projects() {
  const { data: items, isLoading } = usePipeline();
  const built = (items ?? []).filter((i) => i.build_status === "built");

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton h-48 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
        <p className="text-sm text-gray-500 mt-1">
          Apps that have been built from opportunities. Start, stop, and inspect each service.
        </p>
      </div>

      {built.length === 0 ? (
        <div className="text-center py-24">
          <Boxes size={40} className="text-gray-200 mx-auto mb-4" />
          <p className="text-gray-400 text-sm">
            No projects built yet.{" "}
            <Link to="/pipeline" className="text-emerald-600 underline">
              Go to My Pipeline
            </Link>{" "}
            and build an app.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5">
          {built.map((item) => <ProjectCard key={item.id} item={item} />)}
        </div>
      )}
    </div>
  );
}
