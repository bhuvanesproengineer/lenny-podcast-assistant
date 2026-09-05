/**
 * Type definitions mapping strictly to FastAPI backend schemas.
 */

export interface HealthResponse {
  status: "healthy" | "unhealthy" | string;
  database: "connected" | "disconnected" | string;
  error?: string;
}

export interface CreateSessionRequest {
  title?: string;
}

export interface CreateSessionResponse {
  session_id: string;
  title: string;
}

export interface MessageResponse {
  id: number;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface SessionSummaryResponse {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionDetailResponse {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: MessageResponse[];
}

export interface ChatRequest {
  session_id: string;
  message: string;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  sources: string[];
  selected_tool?: "PodcastRAGTool" | "Ship30Tool" | "DirectResponse" | string;
  artifact?: boolean;
  markdown_content?: string;
  html_content?: string;
  word_count?: number;
}

export interface ProviderInfo {
  name: string;
  model: string;
  base_url: string;
  available: boolean;
}

export interface ProviderSettingsResponse {
  active_provider: "ollama" | "cloud" | string;
  local: ProviderInfo;
  cloud: ProviderInfo;
  fallback_enabled: boolean;
}

export interface SetProviderRequest {
  provider: "ollama" | "cloud" | string;
}
