import { useState } from "react";
import { Search, SlidersHorizontal } from "lucide-react";
import OpportunityCard from "@/components/OpportunityCard";
import { useOpportunities, useAddToPipeline } from "@/hooks/useOpportunities";
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

function EmptyState() {
  return (
    <div className="col-span-full flex flex-col items-center justify-center py-24 text-center">
      <Search size={40} className="text-gray-300 mb-4" />
      <h3 className="text-lg font-semibold text-gray-700 mb-1">No opportunities found</h3>
      <p className="text-sm text-gray-400 max-w-xs">
        Try adjusting your filters, or wait for the next scrape cycle to populate data.
      </p>
    </div>
  );
}

export default function Dashboard() {
  const [filters, setFilters] = useState<OpportunityFilters>({
    min_score: 0,
    page: 1,
    page_size: 24,
  });
  const [category, setCategory] = useState("");
  const [minScore, setMinScore] = useState(0);

  const { data, isLoading, isError } = useOpportunities({
    ...filters,
    category: category || undefined,
    min_score: minScore,
  });

  const addMutation = useAddToPipeline();

  const handleSave = (opportunityId: string) => {
    addMutation.mutate({ opportunityId });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Market Opportunities</h1>
        <p className="text-sm text-gray-500 mt-1">
          Sorted by Viability Index — scored from real user complaints, demand signals, and competition data.
        </p>
      </div>

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

        {/* Reset */}
        {(category || minScore > 0) && (
          <button
            onClick={() => {
              setCategory("");
              setMinScore(0);
            }}
            className="text-xs text-gray-400 hover:text-gray-700 underline"
          >
            Reset
          </button>
        )}

        {/* Count */}
        {data && (
          <span className="ml-auto text-xs text-gray-400">
            {data.total} opportunities
          </span>
        )}
      </div>

      {/* Error */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          Failed to load opportunities. Make sure the API is running.
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {isLoading
          ? Array.from({ length: 9 }).map((_, i) => <SkeletonCard key={i} />)
          : data?.items.length === 0
          ? <EmptyState />
          : data?.items.map((opp) => (
              <OpportunityCard
                key={opp.id}
                opportunity={opp}
                onSave={handleSave}
                isSaving={addMutation.isPending && addMutation.variables?.opportunityId === opp.id}
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
