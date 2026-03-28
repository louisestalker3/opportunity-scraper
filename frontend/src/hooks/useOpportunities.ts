import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  getOpportunities,
  getOpportunity,
  getPipelineItems,
  addToPipeline,
  updatePipelineItem,
  removePipelineItem,
  triggerRescore,
  type OpportunityFilters,
  type PaginatedOpportunities,
  type OpportunityDetail,
  type PipelineItem,
} from "@/api/client";

// ─── Query keys ───────────────────────────────────────────────────────────────

export const keys = {
  opportunities: (filters?: OpportunityFilters) =>
    ["opportunities", filters] as const,
  opportunity: (id: string) => ["opportunity", id] as const,
  pipeline: () => ["pipeline"] as const,
};

// ─── Opportunities ────────────────────────────────────────────────────────────

export function useOpportunities(
  filters: OpportunityFilters = {}
): UseQueryResult<PaginatedOpportunities> {
  return useQuery({
    queryKey: keys.opportunities(filters),
    queryFn: () => getOpportunities(filters),
  });
}

export function useOpportunity(id: string): UseQueryResult<OpportunityDetail> {
  return useQuery({
    queryKey: keys.opportunity(id),
    queryFn: () => getOpportunity(id),
    enabled: Boolean(id),
  });
}

export function useRescore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => triggerRescore(id),
    onSuccess: (_data, id) => {
      // Invalidate after a brief delay to let the worker start
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: keys.opportunity(id) });
        queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      }, 2000);
    },
  });
}

// ─── Pipeline ─────────────────────────────────────────────────────────────────

export function usePipeline(): UseQueryResult<PipelineItem[]> {
  return useQuery({
    queryKey: keys.pipeline(),
    queryFn: getPipelineItems,
  });
}

export function useAddToPipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      opportunityId,
      notes,
      status,
    }: {
      opportunityId: string;
      notes?: string;
      status?: string;
    }) => addToPipeline(opportunityId, notes, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

export function useUpdatePipelineItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: { notes?: string | null; status?: string };
    }) => updatePipelineItem(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

export function useRemovePipelineItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => removePipelineItem(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}
