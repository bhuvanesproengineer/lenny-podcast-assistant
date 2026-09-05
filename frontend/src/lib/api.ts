import {
  HealthResponse,
  CreateSessionRequest,
  CreateSessionResponse,
  SessionSummaryResponse,
  SessionDetailResponse,
  ChatRequest,
  ChatResponse,
  ProviderSettingsResponse,
} from "@/types/api";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);

class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  try {
    const res = await fetch(url, {
      ...options,
      headers,
    });

    if (!res.ok) {
      let errorDetail = `Request failed with status ${res.status}`;
      try {
        const errorJson = await res.json();
        errorDetail = errorJson.detail || errorJson.error || errorDetail;
      } catch {
        // Response was not JSON
      }
      throw new ApiError(errorDetail, res.status);
    }

    return (await res.json()) as T;
  } catch (err: any) {
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(
      err.message || "Failed to communicate with backend server",
      0
    );
  }
}

export const api = {
  /**
   * Probes backend and database connectivity.
   */
  async getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },

  /**
   * Creates a new chat session.
   */
  async createSession(title?: string): Promise<CreateSessionResponse> {
    const payload: CreateSessionRequest = title ? { title } : {};
    return request<CreateSessionResponse>("/session/new", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Lists all chat sessions.
   */
  async getSessions(skip = 0, limit = 50): Promise<SessionSummaryResponse[]> {
    return request<SessionSummaryResponse[]>(`/sessions?skip=${skip}&limit=${limit}`);
  },

  /**
   * Retrieves full conversation history for a specific session.
   */
  async getSessionDetails(sessionId: string): Promise<SessionDetailResponse> {
    const cleanId = encodeURIComponent(sessionId.trim());
    return request<SessionDetailResponse>(`/sessions/${cleanId}`);
  },

  /**
   * Alias for getSessionDetails.
   */
  async getSession(sessionId: string): Promise<SessionDetailResponse> {
    return this.getSessionDetails(sessionId);
  },

  /**
   * Renames an existing chat session.
   */
  async renameSession(sessionId: string, title: string): Promise<SessionSummaryResponse> {
    const cleanId = encodeURIComponent(sessionId.trim());
    return request<SessionSummaryResponse>(`/sessions/${cleanId}`, {
      method: "PATCH",
      body: JSON.stringify({ title: title.trim() }),
    });
  },

  /**
   * Deletes a chat session.
   */
  async deleteSession(sessionId: string): Promise<void> {
    const cleanId = encodeURIComponent(sessionId.trim());
    const url = `${API_BASE}/sessions/${cleanId}`;
    const res = await fetch(url, { method: "DELETE" });
    if (!res.ok && res.status !== 204) {
      let errDetail = `Failed to delete session (${res.status})`;
      try {
        const j = await res.json();
        errDetail = j.detail || errDetail;
      } catch {}
      throw new ApiError(errDetail, res.status);
    }
  },

  /**
   * Submits a user message and orchestrates RAG/Agent response.
   * Supports both api.sendMessage(sessionId, message) and api.sendMessage({ session_id, message }).
   */
  async sendMessage(
    arg1: string | { session_id: string; message: string },
    arg2?: string
  ): Promise<ChatResponse> {
    const session_id = typeof arg1 === "string" ? arg1 : arg1.session_id;
    const message = typeof arg1 === "string" ? arg2 || "" : arg1.message;
    const payload: ChatRequest = {
      session_id: session_id.trim(),
      message: message.trim(),
    };
    return request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Downloads a generated document (.docx or .pdf) from the backend export service.
   */
  async downloadExport(format: "docx" | "pdf", markdown: string, title?: string): Promise<void> {
    const url = `${API_BASE}/export/${format}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown, title }),
    });

    if (!res.ok) {
      throw new Error(`Failed to export ${format.toUpperCase()}: ${res.statusText}`);
    }

    const blob = await res.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const safeTitle = (title || "ship30-article")
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .replace(/[-\s]+/g, "-");
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `${safeTitle}.${format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(downloadUrl);
  },

  /**
   * Downloads plain markdown file directly in browser.
   */
  downloadMarkdown(markdown: string, title?: string): void {
    const safeTitle = (title || "ship30-article")
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .replace(/[-\s]+/g, "-");
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8;" });
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `${safeTitle}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(downloadUrl);
  },

  /**
   * Downloads HTML file directly in browser.
   */
  downloadHtml(html: string, title?: string): void {
    const safeTitle = (title || "artifact")
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .replace(/[-\s]+/g, "-");
    const blob = new Blob([html], { type: "text/html;charset=utf-8;" });
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `${safeTitle}.html`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(downloadUrl);
  },

  /**
   * Retrieves active LLM provider configuration and status.
   */
  async getProviderSettings(): Promise<ProviderSettingsResponse> {
    return request<ProviderSettingsResponse>("/settings/provider");
  },

  /**
   * Switches active LLM provider ('ollama' or 'cloud').
   */
  async setProviderSettings(provider: "ollama" | "cloud" | string): Promise<ProviderSettingsResponse> {
    return request<ProviderSettingsResponse>("/settings/provider", {
      method: "POST",
      body: JSON.stringify({ provider }),
    });
  },
};

export { ApiError };
