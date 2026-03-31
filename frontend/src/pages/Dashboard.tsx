import { useState, useCallback } from "react";
import { Search, SlidersHorizontal, Sparkles, Eye, EyeOff, ArrowUpDown } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import OpportunityCard from "@/components/OpportunityCard";
import { useOpportunities, useAddToPipeline, usePipeline, useRankOpportunity, useDeleteOpportunity } from "@/hooks/useOpportunities";
import {
  getDismissedIds,
  dismissOpportunity,
  clearAllDismissed,
  generateIdeas,
} from "@/api/client";
import type { OpportunityFilters } from "@/api/client";

const CATEGORIES = [
  "Project Management",
  "CRM",
  "Marketing",
  "Analytics",
  "Communication",
  "Finance",
  "HR",
  "E-commerce",
  "Developer Tools",
  "Design",
];

function SkeletonCard() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 flex flex-col gap-4">
      <div className="flex justify-between">
        <div className="skeleton h-4 w-32 rounded" />
        <div className="skeleton h-6 w-10 rounded-full" />
      </div>
      <div className="skeleton h-2 w-full rounded-full" />
      <div className="skeleton h-9 w-full rounded-lg" />
      <div className="flex justify-between items-center">
        <div className="skeleton h-3 w-20 rounded" />
        <div className="skeleton h-7 w-16 rounded-lg" />
      </div>
    </div>
  );
}

function EmptyState({ hasDismissed, onShowDismissed }: { hasDismissed: boolean; onShowDismissed: () => void }) {
  return (
    <div className="col-span-full flex flex-col items-center justify-center py-24 text-center">
      <Search size={40} className="text-gray-300 mb-4" />
      <h3 className="text-lg font-semibold text-gray-700 mb-1">No opportunities found</h3>
      <p className="text-sm text-gray-400 max-w-xs">
        Try adjusting your filters, or wait for the next scrape cycle to populate data.
      </p>
      {hasDismissed && (
        <button onClick={onShowDismissed} className="mt-3 text-sm text-gray-500 underline">
          Show dismissed items
        </button>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [filters, setFilters] = useState<OpportunityFilters>({
    min_score: 0,
    sort_by: "viability",
    page: 1,
    page_size: 24,
  });
  const [category, setCategory] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [sortBy, setSortBy] = useState<OpportunityFilters["sort_by"]>("viability");
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(() => getDismissedIds());
  const [showDismissed, setShowDismissed] = useState(false);

  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useOpportunities({
    ...filters,
    category: category || undefined,
    min_score: minScore,
    sort_by: sortBy,
  });

  const { data: pipelineItems } = usePipeline();
  const savedIds = new Set((pipelineItems ?? []).map((i) => i.opportunity_id));

  const addMutation = useAddToPipeline();
  const rankMutation = useRankOpportunity();
  const deleteMutation = useDeleteOpportunity();

  const generateMutation = useMutation({
    mutationFn: ({ count, cat }: { count: number; cat?: string }) =>
      generateIdeas(count, cat || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["opportunities"] });
    },
  });

  const handleSave = (opportunityId: string) => {
    addMutation.mutate({ opportunityId });
  };

  const handleDismiss = useCallback((id: string) => {
    dismissOpportunity(id);
    setDismissedIds(getDismissedIds());
  }, []);

  const handleDelete = useCallback((id: string) => {
    deleteMutation.mutate(id);
    // Also remove from dismissed set if present
    dismissOpportunity(id);
    setDismissedIds(getDismissedIds());
  }, [deleteMutation]);

  const handleRank = useCallback((id: string, rank: number | null) => {
    rankMutation.mutate({ id, rank });
  }, [rankMutation]);

  const handleClearDismissed = () => {
    clearAllDismissed();
    setDismissedIds(new Set());
    setShowDismissed(false);
  };

  const allItems = data?.items ?? [];
  const visibleItems = showDismissed
    ? allItems
    : allItems.filter((o) => !dismissedIds.has(o.id));
  const hiddenCount = allItems.length - visibleItems.length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Market Opportunities</h1>
          <p className="text-sm text-gray-500 mt-1">
            Sorted by Viability Index — scored from real user complaints, demand signals, and competition data.
          </p>
        </div>

        {/* Generate Ideas button */}
        <button
          onClick={() => generateMutation.mutate({ count: 5, cat: category || undefined })}
          disabled={generateMutation.isPending}
          className="shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Sparkles size={15} />
          {generateMutation.isPending ? "Generating…" : "Generate Ideas"}
        </button>
      </div>

      {/* Generate ideas success banner */}
      {generateMutation.isSuccess && (
        <div className="bg-purple-50 border border-purple-200 rounded-xl px-4 py-3 text-sm text-purple-700 flex items-center gap-2">
          <Sparkles size={14} />
          {generateMutation.data?.length ?? 0} new AI-generated ideas added to the list.
        </div>
      )}

      {/* Generate ideas error banner */}
      {generateMutation.isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
          <strong>Could not generate ideas.</strong>{" "}
          {(generateMutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
            ?? "Make sure the claude CLI is installed and authenticated."}
        </div>
      )}

      {/* Filter bar */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 flex flex-wrap gap-4 items-end">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-500">
          <SlidersHorizontal size={15} />
          Filters
        </div>

        {/* Category */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500 font-medium">Category</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-green-500"
          >
            <option value="">All categories</option>
            {CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>

        {/* Min score */}
        <div className="flex flex-col gap-1 min-w-[160px]">
          <label className="text-xs text-gray-500 font-medium">
            Min Viability Score: <span className="text-green-700 font-bold">{minScore}</span>
          </label>
          <input
            type="range"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="w-full accent-green-600"
          />
        </div>

        {/* Sort */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500 font-medium flex items-center gap-1">
            <ArrowUpDown size={11} /> Sort by
          </label>
          <select
            value={sortBy}
            onChange={(e) => {
              setSortBy(e.target.value as OpportunityFilters["sort_by"]);
              setFilters((f) => ({ ...f, page: 1 }));
            }}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-green-500"
          >
            <option value="viability">Viability Score</option>
            <option value="rank">My Rank ★</option>
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
          </select>
        </div>

        {/* Reset */}
        {(category || minScore > 0 || sortBy !== "viability") && (
          <button
            onClick={() => { setCategory(""); setMinScore(0); setSortBy("viability"); }}
            className="text-xs text-gray-400 hover:text-gray-700 underline"
          >
            Reset
          </button>
        )}

        <div className="ml-auto flex items-center gap-3">
          {/* Dismissed toggle */}
          {dismissedIds.size > 0 && (
            <button
              onClick={() => setShowDismissed((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-700 transition-colors"
            >
              {showDismissed ? <EyeOff size={13} /> : <Eye size={13} />}
              {showDismissed ? "Hide dismissed" : `${dismissedIds.size} dismissed`}
            </button>
          )}

          {showDismissed && dismissedIds.size > 0 && (
            <button
              onClick={handleClearDismissed}
              className="text-xs text-red-400 hover:text-red-600 underline"
            >
              Clear all
            </button>
          )}

          {/* Count */}
          {data && (
            <span className="text-xs text-gray-400">
              {visibleItems.length} of {data.total} opportunities
            </span>
          )}
        </div>
      </div>

      {/* Error */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          Failed to load opportunities. Make sure the API is running.
        </div>
      )}

      {/* Hidden items notice */}
      {!showDismissed && hiddenCount > 0 && (
        <div className="text-xs text-gray-400 text-center">
          {hiddenCount} dismissed {hiddenCount === 1 ? "idea" : "ideas"} hidden.{" "}
          <button onClick={() => setShowDismissed(true)} className="underline hover:text-gray-600">
            Show
          </button>
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {isLoading
          ? Array.from({ length: 9 }).map((_, i) => <SkeletonCard key={i} />)
          : visibleItems.length === 0
          ? <EmptyState hasDismissed={dismissedIds.size > 0} onShowDismissed={() => setShowDismissed(true)} />
          : visibleItems.map((opp) => (
              <OpportunityCard
                key={opp.id}
                opportunity={opp}
                onSave={handleSave}
                onDismiss={!showDismissed ? handleDismiss : undefined}
                onDelete={handleDelete}
                onRank={handleRank}
                isSaving={addMutation.isPending && addMutation.variables?.opportunityId === opp.id}
                isSaved={savedIds.has(opp.id)}
              />
            ))}
      </div>

      {/* Pagination */}
      {data && data.total > filters.page_size! && (
        <div className="flex justify-center gap-2 pt-4">
          <button
            disabled={filters.page === 1}
            onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) - 1 }))}
            className="px-4 py-2 text-sm rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
          >
            Previous
          </button>
          <span className="px-4 py-2 text-sm text-gray-500">
            Page {filters.page} of {Math.ceil(data.total / filters.page_size!)}
          </span>
          <button
            disabled={(filters.page ?? 1) * filters.page_size! >= data.total}
            onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) + 1 }))}
            className="px-4 py-2 text-sm rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
