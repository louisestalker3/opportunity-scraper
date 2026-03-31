import { useState } from "react";
import { Link } from "react-router-dom";
import { Trash2, ExternalLink, ChevronDown, FileText, Hammer, CheckCircle2, AlertCircle, BookOpen, RefreshCw, Play, Square, Loader2 } from "lucide-react";
import {
  usePipeline,
  useUpdatePipelineItem,
  useRemovePipelineItem,
  useBuildApp,
  useRegeneratePlan,
  useStartProject,
  useStopProject,
} from "@/hooks/useOpportunities";
import { useOpportunities } from "@/hooks/useOpportunities";
import type { PipelineItem } from "@/api/client";

const COLUMNS: { id: PipelineItem["status"]; label: string; color: string }[] = [
  { id: "watching", label: "Watching", color: "border-blue-300 bg-blue-50" },
  { id: "considering", label: "Considering", color: "border-yellow-300 bg-yellow-50" },
  { id: "building", label: "Building...", color: "border-blue-400 bg-blue-50" },
  { id: "built", label: "Built", color: "border-green-500 bg-green-50" },
  { id: "dropped", label: "Dropped", color: "border-gray-300 bg-gray-100" },
];

function ProposalPanel({ proposal }: { proposal: string }) {
  // Render markdown headings and paragraphs simply without a full md library
  const lines = proposal.split("\n");
  return (
    <div className="text-xs text-gray-700 space-y-2 max-h-96 overflow-y-auto pr-1">
      {lines.map((line, i) => {
        if (line.startsWith("## ")) return <h3 key={i} className="font-bold text-gray-900 text-sm mt-3 first:mt-0">{line.slice(3)}</h3>;
        if (line.startsWith("### ")) return <h4 key={i} className="font-semibold text-gray-800 mt-2">{line.slice(4)}</h4>;
        if (line.startsWith("- ")) return <p key={i} className="pl-3 before:content-['•'] before:mr-2 before:text-gray-400">{line.slice(2)}</p>;
        if (line.startsWith("**") && line.endsWith("**")) return <p key={i} className="font-semibold">{line.slice(2, -2)}</p>;
        if (line.trim() === "") return null;
        return <p key={i} className="leading-relaxed">{line}</p>;
      })}
    </div>
  );
}

function AppPlanPanel({ planJson }: { planJson: string }) {
  try {
    const plan = JSON.parse(planJson);
    const mvp = plan.features?.filter((f: { priority: string }) => f.priority === "mvp") ?? [];
    const v2 = plan.features?.filter((f: { priority: string }) => f.priority === "v2") ?? [];
    return (
      <div className="text-xs text-gray-700 space-y-3 max-h-96 overflow-y-auto pr-1">
        {plan.tagline && <p className="italic text-gray-500">{plan.tagline}</p>}
        {plan.description && <p className="leading-relaxed">{plan.description}</p>}
        {plan.tech_stack && (
          <div>
            <p className="font-semibold text-gray-800 mb-1">Tech Stack</p>
            <ul className="space-y-0.5">
              {Object.entries(plan.tech_stack).map(([k, v]) => (
                <li key={k}><span className="font-medium capitalize">{k}:</span> {String(v)}</li>
              ))}
            </ul>
          </div>
        )}
        {mvp.length > 0 && (
          <div>
            <p className="font-semibold text-gray-800 mb-1">MVP Features</p>
            <ul className="space-y-0.5">
              {mvp.map((f: { name: string; description: string }) => (
                <li key={f.name}><span className="font-medium">{f.name}</span> — {f.description}</li>
              ))}
            </ul>
          </div>
        )}
        {v2.length > 0 && (
          <div>
            <p className="font-semibold text-gray-800 mb-1">v2 Features</p>
            <ul className="space-y-0.5 text-gray-500">
              {v2.map((f: { name: string; description: string }) => (
                <li key={f.name}><span className="font-medium">{f.name}</span> — {f.description}</li>
              ))}
            </ul>
          </div>
        )}
        {plan.mvp_summary && <p className="text-gray-500 italic">{plan.mvp_summary}</p>}
      </div>
    );
  } catch {
    return <p className="text-xs text-gray-400">Could not parse app plan.</p>;
  }
}

function PipelineCard({ item }: { item: PipelineItem }) {
  const updateMutation = useUpdatePipelineItem();
  const removeMutation = useRemovePipelineItem();
  const buildMutation = useBuildApp();
  const regenerateMutation = useRegeneratePlan();
  const startMutation = useStartProject();
  const stopMutation = useStopProject();
  const [editingNotes, setEditingNotes] = useState(false);
  const [notes, setNotes] = useState(item.notes ?? "");
  const [showProposal, setShowProposal] = useState(false);
  const [showPlan, setShowPlan] = useState(false);

  // Fetch opportunity details for display
  const { data: oppsData } = useOpportunities({ page_size: 100 });
  const opp = oppsData?.items.find((o) => o.id === item.opportunity_id);
  const appName = opp?.app_profile?.name ?? "Loading…";
  const score = opp?.viability_score;

  const handleStatusChange = (newStatus: string) => {
    updateMutation.mutate({ id: item.id, payload: { status: newStatus } });
  };

  const handleNotesSave = () => {
    updateMutation.mutate({ id: item.id, payload: { notes } });
    setEditingNotes(false);
  };

  const scoreColor =
    score === null || score === undefined
      ? "text-gray-400"
      : score >= 70
      ? "text-green-600"
      : score >= 40
      ? "text-yellow-600"
      : "text-red-500";

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4 space-y-3">
      {/* App name + score */}
      <div className="flex items-start justify-between gap-2">
        <Link
          to={`/opportunity/${item.opportunity_id}`}
          className="font-semibold text-gray-900 hover:text-green-700 text-sm transition-colors"
        >
          {appName}
        </Link>
        {score !== undefined && (
          <span className={`text-sm font-bold shrink-0 ${scoreColor}`}>
            {score !== null ? score.toFixed(0) : "—"}
          </span>
        )}
      </div>

      {/* Status selector */}
      <div className="relative">
        <select
          value={item.status}
          onChange={(e) => handleStatusChange(e.target.value)}
          disabled={updateMutation.isPending || item.build_status === "building"}
          className="w-full text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 bg-white appearance-none focus:outline-none focus:ring-2 focus:ring-green-500 pr-7 disabled:opacity-50"
        >
          {COLUMNS.map((col) => (
            <option key={col.id} value={col.id}>
              {col.label}
            </option>
          ))}
        </select>
        <ChevronDown size={12} className="absolute right-2 top-2.5 text-gray-400 pointer-events-none" />
      </div>

      {/* Notes */}
      {editingNotes ? (
        <div className="space-y-1.5">
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 resize-none focus:outline-none focus:ring-2 focus:ring-green-500"
            rows={3}
            placeholder="Add notes…"
            autoFocus
          />
          <div className="flex gap-2">
            <button
              onClick={handleNotesSave}
              className="text-xs bg-green-600 text-white rounded px-2.5 py-1 hover:bg-green-700"
            >
              Save
            </button>
            <button
              onClick={() => {
                setNotes(item.notes ?? "");
                setEditingNotes(false);
              }}
              className="text-xs text-gray-400 hover:text-gray-700 px-2"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setEditingNotes(true)}
          className="text-left w-full text-xs text-gray-400 hover:text-gray-700 line-clamp-2 min-h-[20px]"
        >
          {notes || "Click to add notes…"}
        </button>
      )}

      {/* Proposal toggle */}
      {item.proposal && (
        <div className="border-t border-gray-100 pt-2">
          <button
            onClick={() => setShowProposal((v) => !v)}
            className="flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-800 transition-colors w-full"
          >
            <FileText size={12} />
            {showProposal ? "Hide proposal" : "View proposal"}
            <ChevronDown size={11} className={`ml-auto transition-transform ${showProposal ? "rotate-180" : ""}`} />
          </button>
          {showProposal && (
            <div className="mt-3 bg-gray-50 border border-gray-200 rounded-lg p-3">
              <ProposalPanel proposal={item.proposal} />
            </div>
          )}
        </div>
      )}

      {/* App plan toggle */}
      {item.app_plan && (
        <div className="border-t border-gray-100 pt-2">
          <button
            onClick={() => setShowPlan((v) => !v)}
            className="flex items-center gap-1.5 text-xs font-medium text-emerald-600 hover:text-emerald-800 transition-colors w-full"
          >
            <BookOpen size={12} />
            {showPlan ? "Hide app plan" : "View app plan"}
            <ChevronDown size={11} className={`ml-auto transition-transform ${showPlan ? "rotate-180" : ""}`} />
          </button>
          {showPlan && (
            <div className="mt-3 bg-gray-50 border border-gray-200 rounded-lg p-3">
              <AppPlanPanel planJson={item.app_plan} />
            </div>
          )}
        </div>
      )}

      {/* Build button */}
      {item.app_plan && (
        <div className="border-t border-gray-100 pt-2">
          {item.build_status === "built" ? (
            <div className="flex items-center gap-1.5 text-xs font-semibold text-green-700">
              <CheckCircle2 size={13} />
              Built
              {item.built_repo_url && (
                <a href={item.built_repo_url} target="_blank" rel="noopener noreferrer" className="ml-auto text-green-600 hover:underline flex items-center gap-1">
                  GitHub <ExternalLink size={11} />
                </a>
              )}
            </div>
          ) : item.build_status === "building" ? (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-blue-600 animate-pulse">
                <Hammer size={13} />
                Building...
              </div>
              {item.build_log && (
                <div className="bg-gray-900 rounded-lg px-2.5 py-2 text-xs font-mono text-green-400 leading-relaxed max-h-28 overflow-y-auto">
                  {item.build_log.split("\n").map((line, i) => (
                    <div key={i}>{line}</div>
                  ))}
                </div>
              )}
            </div>
          ) : item.build_status === "failed" ? (
            <button
              onClick={() => buildMutation.mutate(item.id)}
              disabled={buildMutation.isPending}
              className="flex items-center gap-1.5 text-xs font-medium text-red-600 hover:text-red-800 w-full"
            >
              <AlertCircle size={12} />
              Build failed — retry
            </button>
          ) : (
            <button
              onClick={() => buildMutation.mutate(item.id)}
              disabled={buildMutation.isPending}
              className="w-full flex items-center justify-center gap-1.5 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-3 py-2 transition-colors disabled:opacity-50"
            >
              <Hammer size={12} />
              Build This App
            </button>
          )}
        </div>
      )}

      {/* Run controls — only show once built */}
      {item.build_status === "built" && (
        <div className="border-t border-gray-100 pt-2">
          {item.run_status === "running" ? (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  Running
                </span>
                {item.run_url && (
                  <a href={item.run_url} target="_blank" rel="noopener noreferrer" className="ml-auto text-xs text-emerald-600 hover:underline flex items-center gap-1">
                    Open <ExternalLink size={11} />
                  </a>
                )}
              </div>
              <button
                onClick={() => stopMutation.mutate(item.id)}
                disabled={stopMutation.isPending}
                className="w-full flex items-center justify-center gap-1.5 text-xs font-semibold bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
              >
                <Square size={11} />
                Stop
              </button>
            </div>
          ) : item.run_status === "starting" ? (
            <div className="flex items-center gap-1.5 text-xs text-blue-600 animate-pulse">
              <Loader2 size={12} className="animate-spin" />
              Starting...
            </div>
          ) : item.run_status === "stopping" ? (
            <div className="flex items-center gap-1.5 text-xs text-gray-500 animate-pulse">
              <Loader2 size={12} className="animate-spin" />
              Stopping...
            </div>
          ) : (
            <button
              onClick={() => startMutation.mutate(item.id)}
              disabled={startMutation.isPending}
              className="w-full flex items-center justify-center gap-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
            >
              <Play size={11} />
              Start App
            </button>
          )}
        </div>
      )}

      {/* Footer actions */}
      <div className="flex items-center justify-between pt-1 border-t border-gray-100">
        <Link
          to={`/opportunity/${item.opportunity_id}`}
          className="text-xs text-green-600 hover:underline flex items-center gap-1"
        >
          View <ExternalLink size={11} />
        </Link>
        <div className="flex items-center gap-2">
          <button
            onClick={() => regenerateMutation.mutate(item.id)}
            disabled={regenerateMutation.isPending}
            className="text-gray-300 hover:text-blue-400 transition-colors disabled:opacity-40"
            title="Regenerate plan & proposal"
          >
            <RefreshCw size={12} className={regenerateMutation.isPending ? "animate-spin" : ""} />
          </button>
          <button
            onClick={() => removeMutation.mutate(item.id)}
            disabled={removeMutation.isPending}
            className="text-gray-300 hover:text-red-400 transition-colors disabled:opacity-40"
            title="Remove from pipeline"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}

function EmptyColumn() {
  return (
    <div className="border-2 border-dashed border-gray-200 rounded-xl p-6 text-center text-xs text-gray-400">
      No items yet
    </div>
  );
}

export default function Pipeline() {
  const { data: items, isLoading, isError } = usePipeline();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">My Pipeline</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {COLUMNS.map((col) => (
            <div key={col.id} className="space-y-3">
              <div className="skeleton h-5 w-24 rounded" />
              <div className="skeleton h-32 w-full rounded-xl" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-center py-24">
        <p className="text-gray-500 text-sm">Failed to load pipeline. Make sure the API is running.</p>
      </div>
    );
  }

  const byStatus = (status: PipelineItem["status"]) =>
    (items ?? []).filter((i) => i.status === status);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">My Pipeline</h1>
        <p className="text-sm text-gray-500 mt-1">
          Track opportunities you are watching, evaluating, or building.
        </p>
      </div>

      {/* Kanban columns */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 items-start">
        {COLUMNS.map((col) => {
          const colItems = byStatus(col.id);
          return (
            <div key={col.id} className="space-y-3">
              {/* Column header */}
              <div
                className={`flex items-center justify-between px-3 py-2 rounded-xl border-l-4 ${col.color}`}
              >
                <span className="text-xs font-bold text-gray-700 uppercase tracking-wide">
                  {col.label}
                </span>
                <span className="text-xs bg-white text-gray-500 rounded-full px-2 py-0.5 border border-gray-200">
                  {colItems.length}
                </span>
              </div>

              {/* Cards */}
              {colItems.length === 0 ? (
                <EmptyColumn />
              ) : (
                colItems.map((item) => <PipelineCard key={item.id} item={item} />)
              )}
            </div>
          );
        })}
      </div>

      {/* Empty state */}
      {(items ?? []).length === 0 && (
        <div className="text-center py-16">
          <p className="text-gray-400 text-sm">
            Your pipeline is empty.{" "}
            <Link to="/" className="text-green-600 underline">
              Browse opportunities
            </Link>{" "}
            and click "Save" to add them here.
          </p>
        </div>
      )}
    </div>
  );
}
