import axios from "axios";
import { v4 as uuidv4 } from "uuid";

// ─── Session ID ───────────────────────────────────────────────────────────────

function getOrCreateSessionId(): string {
  const key = "opp_session_id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = uuidv4();
    localStorage.setItem(key, id);
  }
  return id;
}

export const sessionId = getOrCreateSessionId();

// ─── Axios instance ───────────────────────────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_URL || "";

export const api = axios.create({
  baseURL: BASE_URL,
  headers: {
    "Content-Type": "application/json",
    "X-Session-ID": sessionId,
  },
});

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AppProfileSummary {
  id: string;
  name: string;
  url: string;
  category: string | null;
  description: string | null;
  avg_review_score: number | null;
  total_reviews: number;
  pros: string[];
  cons: string[];
}

export interface Opportunity {
  id: string;
  app_profile_id: string;
  viability_score: number | null;
  market_demand_score: number;
  complaint_severity_score: number;
  competition_density_score: number;
  pricing_gap_score: number;
  build_complexity_score: number;
  differentiation_score: number;
  mention_count: number;
  complaint_count: number;
  alternative_seeking_count: number;
  ai_rationale: string | null;
  source: string;
  user_rank: number | null;
  created_at: string;
  app_profile: AppProfileSummary | null;
}

export interface MentionSummary {
  id: string;
  source: string;
  content: string;
  url: string;
  sentiment: string;
  signal_type: string;
  confidence_score: number;
  scraped_at: string;
}

export interface OpportunityDetail extends Opportunity {
  recent_mentions: MentionSummary[];
}

export interface PaginatedOpportunities {
  items: Opportunity[];
  total: number;
  page: number;
  page_size: number;
}

export interface AppProfile {
  id: string;
  name: string;
  url: string;
  category: string | null;
  description: string | null;
  pricing_tiers: unknown[];
  target_audience: string | null;
  avg_review_score: number | null;
  total_reviews: number;
  pros: string[];
  cons: string[];
  competitor_ids: string[];
  first_seen: string;
  last_updated: string;
  recent_mentions?: MentionSummary[];
  competitors?: AppProfile[];
}

export interface PipelineItem {
  id: string;
  opportunity_id: string;
  user_session_id: string;
  notes: string | null;
  proposal: string | null;
  app_plan: string | null;  // JSON string
  status: "watching" | "considering" | "building" | "built" | "dropped";
  build_status: "building" | "built" | "failed" | null;
  built_repo_url: string | null;
  build_log: string | null;
  run_status: "starting" | "running" | "stopping" | "stopped" | "failed" | null;
  run_url: string | null;
  chosen_name: string | null;
  chosen_logo_svg: string | null;
  chosen_logo_colors: { primary: string; secondary: string; accent: string } | null;
  created_at: string;
  updated_at: string;
}

// ─── Opportunities ────────────────────────────────────────────────────────────

export interface OpportunityFilters {
  category?: string;
  min_score?: number;
  max_competition?: number;
  sort_by?: "viability" | "rank" | "newest" | "oldest";
  page?: number;
  page_size?: number;
}

export async function getOpportunities(
  filters: OpportunityFilters = {}
): Promise<PaginatedOpportunities> {
  const { data } = await api.get<PaginatedOpportunities>("/api/opportunities", {
    params: filters,
  });
  return data;
}

export async function getOpportunity(id: string): Promise<OpportunityDetail> {
  const { data } = await api.get<OpportunityDetail>(`/api/opportunities/${id}`);
  return data;
}

export async function triggerRescore(id: string): Promise<void> {
  await api.post(`/api/opportunities/${id}/trigger-rescore`);
}

export async function rankOpportunity(id: string, rank: number | null): Promise<Opportunity> {
  const { data } = await api.patch<Opportunity>(`/api/opportunities/${id}`, { user_rank: rank });
  return data;
}

export async function deleteOpportunity(id: string): Promise<void> {
  await api.delete(`/api/opportunities/${id}`);
}

// ─── Apps ─────────────────────────────────────────────────────────────────────

export interface AppFilters {
  category?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export async function getApps(filters: AppFilters = {}): Promise<AppProfile[]> {
  const { data } = await api.get<AppProfile[]>("/api/apps", { params: filters });
  return data;
}

export async function getApp(id: string): Promise<AppProfile> {
  const { data } = await api.get<AppProfile>(`/api/apps/${id}`);
  return data;
}

// ─── Pipeline ─────────────────────────────────────────────────────────────────

export async function getPipelineItems(): Promise<PipelineItem[]> {
  const { data } = await api.get<PipelineItem[]>("/api/pipeline");
  return data;
}

export async function addToPipeline(
  opportunityId: string,
  notes?: string,
  status = "watching"
): Promise<PipelineItem> {
  const { data } = await api.post<PipelineItem>("/api/pipeline", {
    opportunity_id: opportunityId,
    notes,
    status,
  });
  return data;
}

export async function updatePipelineItem(
  id: string,
  payload: { notes?: string | null; status?: string }
): Promise<PipelineItem> {
  const { data } = await api.patch<PipelineItem>(`/api/pipeline/${id}`, payload);
  return data;
}

export async function removePipelineItem(id: string): Promise<void> {
  await api.delete(`/api/pipeline/${id}`);
}

export async function triggerBuild(id: string): Promise<void> {
  await api.post(`/api/pipeline/${id}/build`);
}

export async function regeneratePlan(id: string): Promise<PipelineItem> {
  const { data } = await api.post<PipelineItem>(`/api/pipeline/${id}/regenerate`);
  return data;
}

export interface ProjectPorts {
  slug: string;
  ports: Record<string, Array<{ host: number; container: number }>>;
}

export interface ServiceInfo {
  name: string;
  ports: Array<{ host: number; container: number }>;
}

export interface ProjectServices {
  slug: string;
  services: ServiceInfo[];
}

export interface ServiceLogs {
  service: string;
  lines: string[];
}

export async function getProjectPorts(id: string): Promise<ProjectPorts> {
  const { data } = await api.get<ProjectPorts>(`/api/pipeline/${id}/ports`);
  return data;
}

export async function getProjectServices(id: string): Promise<ProjectServices> {
  const { data } = await api.get<ProjectServices>(`/api/pipeline/${id}/services`);
  return data;
}

export async function getServiceLogs(id: string, service: string, tail = 200): Promise<ServiceLogs> {
  const { data } = await api.get<ServiceLogs>(`/api/pipeline/${id}/logs/${service}`, { params: { tail } });
  return data;
}

export async function forceStopProject(id: string): Promise<void> {
  await api.post(`/api/pipeline/${id}/force-stop`);
}

export async function startProject(id: string): Promise<void> {
  await api.post(`/api/pipeline/${id}/start`);
}

export async function stopProject(id: string): Promise<void> {
  await api.post(`/api/pipeline/${id}/stop`);
}

// ─── Name Suggestions ────────────────────────────────────────────────────────

export interface NameSuggestion {
  id: string;
  name: string;
  tagline: string | null;
  rationale: string | null;
  status: "suggested" | "chosen" | "rejected";
  created_at: string;
}

export async function getNameSuggestions(itemId: string): Promise<NameSuggestion[]> {
  const { data } = await api.get<NameSuggestion[]>(`/api/pipeline/${itemId}/names`);
  return data;
}

export async function generateNames(itemId: string, count = 6, hint?: string): Promise<NameSuggestion[]> {
  const { data } = await api.post<NameSuggestion[]>(`/api/pipeline/${itemId}/names/generate`, { count, hint: hint || null });
  return data;
}

export async function selectName(itemId: string, nameId: string): Promise<{ chosen_name: string }> {
  const { data } = await api.post(`/api/pipeline/${itemId}/names/${nameId}/select`);
  return data;
}

export async function deleteName(itemId: string, nameId: string): Promise<void> {
  await api.delete(`/api/pipeline/${itemId}/names/${nameId}`);
}

export async function setManualName(itemId: string, name: string): Promise<NameSuggestion> {
  const { data } = await api.post<NameSuggestion>(`/api/pipeline/${itemId}/names/set-manual`, { name });
  return data;
}

// ─── Logo Suggestions ────────────────────────────────────────────────────────

export interface LogoSuggestion {
  id: string;
  concept_name: string;
  description: string | null;
  svg_content: string;
  color_palette: { primary: string; secondary: string; accent: string };
  style: string;
  status: "suggested" | "chosen" | "rejected";
  created_at: string;
}

export async function getLogoSuggestions(itemId: string): Promise<LogoSuggestion[]> {
  const { data } = await api.get<LogoSuggestion[]>(`/api/pipeline/${itemId}/logos`);
  return data;
}

export async function generateLogos(itemId: string, count = 3): Promise<LogoSuggestion[]> {
  const { data } = await api.post<LogoSuggestion[]>(`/api/pipeline/${itemId}/logos/generate`, { count });
  return data;
}

export async function selectLogo(itemId: string, logoId: string): Promise<void> {
  await api.post(`/api/pipeline/${itemId}/logos/${logoId}/select`);
}

export async function deleteLogo(itemId: string, logoId: string): Promise<void> {
  await api.delete(`/api/pipeline/${itemId}/logos/${logoId}`);
}

export async function uploadLogo(itemId: string, file: File): Promise<LogoSuggestion> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<LogoSuggestion>(`/api/pipeline/${itemId}/logos/upload`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

// ─── Project Tasks ────────────────────────────────────────────────────────────

export type TaskStatus = "draft" | "ready" | "in_progress" | "done" | "waiting_for_agent" | "paused";
export type TaskType = "feature" | "bug" | "fix" | "improvement";
export type TaskPriority = "low" | "medium" | "high";

export interface ProjectTask {
  id: string;
  pipeline_item_id: string;
  type: TaskType;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  agent_response: string | null;
  retry_after: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export async function getTasks(itemId: string): Promise<ProjectTask[]> {
  const { data } = await api.get<ProjectTask[]>(`/api/pipeline/${itemId}/tasks`);
  return data;
}

export async function createTask(
  itemId: string,
  payload: { type: TaskType; title: string; description?: string; priority?: TaskPriority; status?: TaskStatus }
): Promise<ProjectTask> {
  const { data } = await api.post<ProjectTask>(`/api/pipeline/${itemId}/tasks`, payload);
  return data;
}

export async function updateTask(
  itemId: string,
  taskId: string,
  payload: { type?: TaskType; title?: string; description?: string; priority?: TaskPriority; status?: TaskStatus }
): Promise<ProjectTask> {
  const { data } = await api.patch<ProjectTask>(`/api/pipeline/${itemId}/tasks/${taskId}`, payload);
  return data;
}

export async function deleteTask(itemId: string, taskId: string): Promise<void> {
  await api.delete(`/api/pipeline/${itemId}/tasks/${taskId}`);
}

// ─── Clone Analysis ───────────────────────────────────────────────────────────

export interface CloneAnalysisResult {
  verdict: "worth_building" | "risky" | "not_worth_it";
  verdict_score: number;
  verdict_summary: string;
  market_size: string;
  growth_trend: "growing" | "stable" | "declining";
  top_complaints: string[];
  competitors: Array<{ name: string; weakness: string }>;
  differentiation_angles: string[];
  pricing_gap: string;
  build_complexity: "low" | "medium" | "high";
  time_to_mvp: string;
  ideal_target: string;
  biggest_risk: string;
  report: string;
}

export async function analyzeClone(
  app_name: string,
  app_url?: string,
  extra_context?: string
): Promise<CloneAnalysisResult> {
  const { data } = await api.post<CloneAnalysisResult>("/api/analyze/clone", {
    app_name,
    app_url: app_url || null,
    extra_context: extra_context || null,
  });
  return data;
}

// ─── AI Idea Generation ───────────────────────────────────────────────────────

export interface GeneratedIdeaResponse {
  opportunity_id: string;
  app_profile_id: string;
  name: string;
  tagline: string;
  category: string | null;
  description: string;
  viability_score: number;
  market_demand_score: number;
  complaint_severity_score: number;
  competition_density_score: number;
  pricing_gap_score: number;
  build_complexity_score: number;
  differentiation_score: number;
  ai_rationale: string;
}

export async function generateIdeas(
  count = 5,
  category?: string
): Promise<GeneratedIdeaResponse[]> {
  const { data } = await api.post<GeneratedIdeaResponse[]>("/api/ideas/generate", {
    count,
    category: category || null,
  });
  return data;
}

// ─── Settings ─────────────────────────────────────────────────────────────────

export interface SettingsResponse {
  repos_path: string;
}

export interface ScannedRepo {
  slug: string;
  path: string;
  remote: string | null;
  description: string | null;
  already_tracked: boolean;
  pipeline_item_id: string | null;
}

export interface ScanResult {
  repos_path: string;
  found: ScannedRepo[];
  imported: number;
}

export async function getSettings(): Promise<SettingsResponse> {
  const { data } = await api.get<SettingsResponse>("/api/settings");
  return data;
}

export async function patchSettings(repos_path: string): Promise<SettingsResponse> {
  const { data } = await api.patch<SettingsResponse>("/api/settings", { repos_path });
  return data;
}

export async function scanRepos(): Promise<ScanResult> {
  const { data } = await api.post<ScanResult>("/api/settings/scan-repos");
  return data;
}

export interface MigrateResult {
  queued: number;
  already_done: number;
  total: number;
}

export async function migrateProjects(): Promise<MigrateResult> {
  const { data } = await api.post<MigrateResult>("/api/settings/migrate-projects");
  return data;
}

// ─── Dismissed Opportunities (localStorage) ───────────────────────────────────

const DISMISSED_KEY = "dismissed_opportunity_ids";

export function getDismissedIds(): Set<string> {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
}

export function dismissOpportunity(id: string): void {
  const ids = getDismissedIds();
  ids.add(id);
  localStorage.setItem(DISMISSED_KEY, JSON.stringify([...ids]));
}

export function undismissOpportunity(id: string): void {
  const ids = getDismissedIds();
  ids.delete(id);
  localStorage.setItem(DISMISSED_KEY, JSON.stringify([...ids]));
}

export function clearAllDismissed(): void {
  localStorage.removeItem(DISMISSED_KEY);
}
