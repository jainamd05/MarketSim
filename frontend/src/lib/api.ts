import type {
  AgentEvent, AnalysisStatus, AppConfig, BusinessProfile, BusinessProfileInput, CompetitorsResponse, DataMode,
  EvidenceResponse, ReportResponse, SimInputs, StrategiesResponse, StrategySimulation, TrendsResponse,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the MarketSim API. Is the backend running on port 8000?");
  }
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    const err = body?.error ?? {};
    throw new ApiError(resp.status, err.code ?? "http_error", err.message ?? `Request failed (${resp.status})`, err.details);
  }
  return body as T;
}

export const api = {
  config: () => request<AppConfig>("/api/config"),
  demoProfile: () => request<BusinessProfileInput>("/api/onboarding/demo-profile"),
  createProfile: (profile: BusinessProfileInput, status: "draft" | "confirmed" = "draft") =>
    request<{ profile: BusinessProfile }>("/api/profiles", { method: "POST", body: JSON.stringify({ profile, status }) }),
  updateProfile: (id: string, profile: BusinessProfileInput, status: "draft" | "confirmed" = "draft") =>
    request<{ profile: BusinessProfile }>(`/api/profiles/${id}`, { method: "PUT", body: JSON.stringify({ profile, status }) }),
  createAnalysis: (profile_id: string, mode?: DataMode) =>
    request<{ analysis_id: string; mode: DataMode; status: string }>("/api/analyses", {
      method: "POST",
      body: JSON.stringify(mode ? { profile_id, mode } : { profile_id }),
    }),
  listAnalyses: () => request<{ id: string; mode: DataMode; status: string; created_at: string; category: string; business_type: string }[]>("/api/analyses?limit=5"),
  analysis: (id: string) => request<AnalysisStatus>(`/api/analyses/${id}`),
  events: (id: string, after = 0) =>
    request<{ analysis_id: string; status: string; events: AgentEvent[]; last_seq: number }>(`/api/analyses/${id}/events?after=${after}`),
  competitors: (id: string) => request<CompetitorsResponse>(`/api/analyses/${id}/competitors`),
  trends: (id: string) => request<TrendsResponse>(`/api/analyses/${id}/trends`),
  strategies: (id: string) => request<StrategiesResponse>(`/api/analyses/${id}/strategies`),
  report: (id: string) => request<ReportResponse>(`/api/analyses/${id}/report`),
  evidence: (id: string) => request<EvidenceResponse>(`/api/analyses/${id}/evidence`),
  simulate: (id: string, strategy_key: string, inputs: SimInputs, inventory_budget?: number | null) =>
    request<{ simulation: StrategySimulation; serpapi_requests_made: number; note: string }>(`/api/analyses/${id}/simulate`, {
      method: "POST",
      body: JSON.stringify({ strategy_key, inputs, ...(inventory_budget != null ? { inventory_budget } : {}) }),
    }),
};
