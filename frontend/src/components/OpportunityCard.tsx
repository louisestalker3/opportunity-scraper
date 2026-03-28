import { Link } from "react-router-dom";
import { PlusCircle, MessageSquare, AlertCircle, ExternalLink } from "lucide-react";
import ScoreBar from "./ScoreBar";
import type { Opportunity } from "@/api/client";

interface OpportunityCardProps {
  opportunity: Opportunity;
  onSave?: (opportunityId: string) => void;
  isSaving?: boolean;
}

function viabilityBadgeClasses(score: number | null): string {
  if (score === null) return "bg-gray-100 text-gray-500";
  if (score >= 70) return "bg-green-100 text-green-800";
  if (score >= 40) return "bg-yellow-100 text-yellow-800";
  return "bg-red-100 text-red-700";
}

export default function OpportunityCard({
  opportunity,
  onSave,
  isSaving = false,
}: OpportunityCardProps) {
  const { app_profile: app } = opportunity;
  const score = opportunity.viability_score;
  const topCon = app?.cons?.[0];

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow p-5 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to={`/opportunity/${opportunity.id}`}
            className="font-semibold text-gray-900 hover:text-green-700 transition-colors text-base truncate block"
          >
            {app?.name ?? "Unknown App"}
          </Link>
          {app?.category && (
            <span className="text-xs text-gray-400 mt-0.5 block">{app.category}</span>
          )}
        </div>

        {/* Viability badge */}
        <div
          className={`shrink-0 px-2.5 py-0.5 rounded-full text-sm font-bold ${viabilityBadgeClasses(score)}`}
        >
          {score !== null ? score.toFixed(0) : "—"}
        </div>
      </div>

      {/* Score bar */}
      <ScoreBar score={score ?? 0} height="sm" showValue={false} />

      {/* Top con */}
      {topCon ? (
        <div className="flex items-start gap-2 text-sm text-gray-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
          <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
          <span className="line-clamp-2">{topCon}</span>
        </div>
      ) : (
        <div className="h-9" /> // Placeholder to keep card heights consistent
      )}

      {/* Footer */}
      <div className="flex items-center justify-between mt-auto">
        <div className="flex items-center gap-1.5 text-xs text-gray-400">
          <MessageSquare size={13} />
          <span>{opportunity.mention_count.toLocaleString()} mentions</span>
        </div>

        <div className="flex items-center gap-2">
          {app?.url && (
            <a
              href={app.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 hover:text-gray-600 transition-colors"
              title="Visit site"
            >
              <ExternalLink size={14} />
            </a>
          )}

          {onSave && (
            <button
              onClick={() => onSave(opportunity.id)}
              disabled={isSaving}
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <PlusCircle size={13} />
              {isSaving ? "Saving..." : "Save"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
