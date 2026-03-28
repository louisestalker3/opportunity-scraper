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
  status: "watching" | "considering" | "building" | "dropped";
  created_at: string;
  updated_at: string;
}

// ─── Opportunities ────────────────────────────────────────────────────────────

export interface OpportunityFilters {
  category?: string;
  min_score?: number;
  max_competition?: number;
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
