import { useState } from "react";
import { Link } from "react-router-dom";
import { Trash2, ExternalLink, ChevronDown } from "lucide-react";
import {
  usePipeline,
  useUpdatePipelineItem,
  useRemovePipelineItem,
} from "@/hooks/useOpportunities";
import { useOpportunities } from "@/hooks/useOpportunities";
import type { PipelineItem } from "@/api/client";

const COLUMNS: { id: PipelineItem["status"]; label: string; color: string }[] = [
  { id: "watching", label: "Watching", color: "border-blue-300 bg-blue-50" },
  { id: "considering", label: "Considering", color: "border-yellow-300 bg-yellow-50" },
  { id: "building", label: "Building", color: "border-green-400 bg-green-50" },
  { id: "dropped", label: "Dropped", color: "border-gray-300 bg-gray-100" },
];

function PipelineCard({ item }: { item: PipelineItem }) {
  const updateMutation = useUpdatePipelineItem();
  const removeMutation = useRemovePipelineItem();
  const [editingNotes, setEditingNotes] = useState(false);
  const [notes, setNotes] = useState(item.notes ?? "");

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
          disabled={updateMutation.isPending}
          className="w-full text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 bg-white appearance-none focus:outline-none focus:ring-2 focus:ring-green-500 pr-7"
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

      {/* Footer actions */}
      <div className="flex items-center justify-between pt-1 border-t border-gray-100">
        <Link
          to={`/opportunity/${item.opportunity_id}`}
          className="text-xs text-green-600 hover:underline flex items-center gap-1"
        >
          View <ExternalLink size={11} />
        </Link>
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
