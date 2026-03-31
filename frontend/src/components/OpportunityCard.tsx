import { useState } from "react";
import { Link } from "react-router-dom";
import { PlusCircle, CheckCircle2, MessageSquare, AlertCircle, ExternalLink, X, Sparkles, Trash2, Star } from "lucide-react";
import ScoreBar from "./ScoreBar";
import type { Opportunity } from "@/api/client";

interface OpportunityCardProps {
  opportunity: Opportunity;
  onSave?: (opportunityId: string) => void;
  onDismiss?: (opportunityId: string) => void;
  onDelete?: (opportunityId: string) => void;
  onRank?: (opportunityId: string, rank: number | null) => void;
  isSaving?: boolean;
  isSaved?: boolean;
}

function viabilityBadgeClasses(score: number | null): string {
  if (score === null) return "bg-gray-100 text-gray-500";
  if (score >= 70) return "bg-green-100 text-green-800";
  if (score >= 40) return "bg-yellow-100 text-yellow-800";
  return "bg-red-100 text-red-700";
}

function StarRating({
  rank,
  onRate,
}: {
  rank: number | null;
  onRate: (r: number | null) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const display = hover ?? rank ?? 0;

  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          onClick={() => onRate(rank === star ? null : star)}
          onMouseEnter={() => setHover(star)}
          onMouseLeave={() => setHover(null)}
          title={rank === star ? "Clear rank" : `Rank ${star}`}
          className="p-0.5 transition-colors"
        >
          <Star
            size={13}
            className={display >= star ? "text-amber-400 fill-amber-400" : "text-gray-200"}
          />
        </button>
      ))}
    </div>
  );
}

export default function OpportunityCard({
  opportunity,
  onSave,
  onDismiss,
  onDelete,
  onRank,
  isSaving = false,
  isSaved = false,
}: OpportunityCardProps) {
  const { app_profile: app } = opportunity;
  const score = opportunity.viability_score;
  const topCon = app?.cons?.[0];
  const isAiGenerated = opportunity.source === "ai_generated";
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleDelete = () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
    } else {
      onDelete?.(opportunity.id);
    }
  };

  return (
    <div className={`bg-white rounded-xl border shadow-sm hover:shadow-md transition-shadow p-5 flex flex-col gap-4 ${isSaved ? "border-green-400 ring-1 ring-green-200" : "border-gray-200"}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Link
              to={`/opportunity/${opportunity.id}`}
              className="font-semibold text-gray-900 hover:text-green-700 transition-colors text-base truncate block"
            >
              {app?.name ?? "Unknown App"}
            </Link>
            {isAiGenerated && (
              <span className="shrink-0 flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700 border border-purple-200">
                <Sparkles size={10} />
                AI
              </span>
            )}
          </div>
          {app?.category && (
            <span className="text-xs text-gray-400 mt-0.5 block">{app.category}</span>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {/* Viability badge */}
          <div className={`px-2.5 py-0.5 rounded-full text-sm font-bold ${viabilityBadgeClasses(score)}`}>
            {score !== null ? score.toFixed(0) : "—"}
          </div>

          {/* Dismiss (hide locally) */}
          {onDismiss && (
            <button
              onClick={() => onDismiss(opportunity.id)}
              title="Hide from view"
              className="p-1 rounded-md text-gray-300 hover:text-gray-500 hover:bg-gray-100 transition-colors"
            >
              <X size={14} />
            </button>
          )}

          {/* Delete (permanent) */}
          {onDelete && (
            <button
              onClick={handleDelete}
              title={confirmDelete ? "Click again to confirm delete" : "Delete permanently"}
              className={`p-1 rounded-md transition-colors ${
                confirmDelete
                  ? "text-red-600 bg-red-50 hover:bg-red-100"
                  : "text-gray-300 hover:text-red-400 hover:bg-gray-100"
              }`}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {/* AI rationale / top complaint */}
      {isAiGenerated && opportunity.ai_rationale ? (
        <div className="flex items-start gap-2 text-sm text-gray-600 bg-purple-50 border border-purple-100 rounded-lg px-3 py-2">
          <Sparkles size={14} className="text-purple-400 mt-0.5 shrink-0" />
          <span className="line-clamp-2">{opportunity.ai_rationale}</span>
        </div>
      ) : topCon ? (
        <div className="flex items-start gap-2 text-sm text-gray-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
          <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
          <span className="line-clamp-2">{topCon}</span>
        </div>
      ) : (
        <div className="h-9" />
      )}

      {/* Score bar */}
      <ScoreBar score={score ?? 0} height="sm" showValue={false} />

      {/* Footer */}
      <div className="flex items-center justify-between mt-auto gap-2">
        <div className="flex items-center gap-3">
          {/* Star rating */}
          {onRank && (
            <StarRating
              rank={opportunity.user_rank}
              onRate={(r) => onRank(opportunity.id, r)}
            />
          )}

          {/* Mention count or AI label */}
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            {isAiGenerated ? (
              <span className="text-purple-400 font-medium">AI Generated</span>
            ) : (
              <>
                <MessageSquare size={13} />
                <span>{opportunity.mention_count.toLocaleString()} mentions</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
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
            isSaved ? (
              <span className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-green-50 text-green-700 border border-green-200">
                <CheckCircle2 size={13} />
                Saved
              </span>
            ) : (
              <button
                onClick={() => onSave(opportunity.id)}
                disabled={isSaving}
                className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <PlusCircle size={13} />
                {isSaving ? "Saving..." : "Save"}
              </button>
            )
          )}
        </div>
      </div>
    </div>
  );
}
