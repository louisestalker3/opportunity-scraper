import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  getOpportunities,
  getOpportunity,
  rankOpportunity,
  deleteOpportunity,
  getPipelineItems,
  addToPipeline,
  updatePipelineItem,
  removePipelineItem,
  triggerRescore,
  triggerBuild,
  regeneratePlan,
  startProject,
  stopProject,
  forceStopProject,
  getProjectPorts,
  getProjectServices,
  getServiceLogs,
  getNameSuggestions,
  generateNames,
  selectName,
  deleteName,
  setManualName,
  getLogoSuggestions,
  generateLogos,
  selectLogo,
  deleteLogo,
  uploadLogo,
  getTasks,
  createTask,
  updateTask,
  deleteTask,
  type OpportunityFilters,
  type PaginatedOpportunities,
  type OpportunityDetail,
  type PipelineItem,
  type ProjectPorts,
  type ProjectServices,
  type ServiceLogs,
  type NameSuggestion,
  type LogoSuggestion,
  type ProjectTask,
  type TaskType,
  type TaskPriority,
  type TaskStatus,
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

export function useRankOpportunity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, rank }: { id: string; rank: number | null }) => rankOpportunity(id, rank),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["opportunities"] });
    },
  });
}

export function useDeleteOpportunity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteOpportunity(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["opportunities"] });
    },
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
    // Poll every 2s while any item is building or transitioning run state
    refetchInterval: (query) => {
      const items = query.state.data;
      const active = items?.some(
        (i) => i.build_status === "building" || i.run_status === "starting" || i.run_status === "stopping"
      );
      return active ? 2000 : false;
    },
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
      queryClient.invalidateQueries({ queryKey: ["opportunities"] });
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

export function useBuildApp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => triggerBuild(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

export function useRegeneratePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => regeneratePlan(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

export function useProjectPorts(id: string | undefined, enabled: boolean) {
  return useQuery<ProjectPorts>({
    queryKey: ["project-ports", id],
    queryFn: () => getProjectPorts(id!),
    enabled: Boolean(id) && enabled,
    staleTime: 30_000,
  });
}

export function useProjectServices(id: string | undefined, enabled: boolean) {
  return useQuery<ProjectServices>({
    queryKey: ["project-services", id],
    queryFn: () => getProjectServices(id!),
    enabled: Boolean(id) && enabled,
    staleTime: 60_000,
  });
}

export function useServiceLogs(id: string | undefined, service: string, enabled: boolean) {
  return useQuery<ServiceLogs>({
    queryKey: ["service-logs", id, service],
    queryFn: () => getServiceLogs(id!, service),
    enabled: Boolean(id) && Boolean(service) && enabled,
    refetchInterval: enabled ? 3000 : false,
    staleTime: 0,
  });
}

export function useForceStopProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => forceStopProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

export function useStartProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => startProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

export function useStopProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => stopProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

// ─── Name Suggestions ────────────────────────────────────────────────────────

export function useNameSuggestions(itemId: string) {
  return useQuery<NameSuggestion[]>({
    queryKey: ["names", itemId],
    queryFn: () => getNameSuggestions(itemId),
    enabled: Boolean(itemId),
  });
}

export function useGenerateNames(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ count, hint }: { count: number; hint?: string }) =>
      generateNames(itemId, count, hint),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["names", itemId] });
    },
  });
}

export function useSelectName(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (nameId: string) => selectName(itemId, nameId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["names", itemId] });
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

export function useDeleteName(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (nameId: string) => deleteName(itemId, nameId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["names", itemId] });
    },
  });
}

export function useSetManualName(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => setManualName(itemId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["names", itemId] });
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

// ─── Logo Suggestions ────────────────────────────────────────────────────────

export function useLogoSuggestions(itemId: string) {
  return useQuery<LogoSuggestion[]>({
    queryKey: ["logos", itemId],
    queryFn: () => getLogoSuggestions(itemId),
    enabled: Boolean(itemId),
  });
}

export function useGenerateLogos(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (count: number) => generateLogos(itemId, count),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["logos", itemId] });
    },
  });
}

export function useSelectLogo(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (logoId: string) => selectLogo(itemId, logoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["logos", itemId] });
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

export function useDeleteLogo(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (logoId: string) => deleteLogo(itemId, logoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["logos", itemId] });
    },
  });
}

export function useUploadLogo(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadLogo(itemId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["logos", itemId] });
      queryClient.invalidateQueries({ queryKey: keys.pipeline() });
    },
  });
}

// ─── Project Tasks ────────────────────────────────────────────────────────────

export function useTasks(itemId: string) {
  return useQuery<ProjectTask[]>({
    queryKey: ["tasks", itemId],
    queryFn: () => getTasks(itemId),
    enabled: Boolean(itemId),
    // Poll every 3s when any task is in_progress or waiting
    refetchInterval: (query) => {
      const tasks = query.state.data;
      const active = tasks?.some((t) =>
        t.status === "in_progress" || t.status === "waiting_for_agent"
      );
      return active ? 3000 : 10000;
    },
  });
}

export function useCreateTask(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { type: TaskType; title: string; description?: string; priority?: TaskPriority; status?: TaskStatus }) =>
      createTask(itemId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks", itemId] });
    },
  });
}

export function useUpdateTask(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, payload }: { taskId: string; payload: Parameters<typeof updateTask>[2] }) =>
      updateTask(itemId, taskId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks", itemId] });
    },
  });
}

export function useDeleteTask(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => deleteTask(itemId, taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks", itemId] });
    },
  });
}
