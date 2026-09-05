export type ArtifactTab = "preview" | "markdown" | "html";

export interface ArtifactData {
  id: string;
  title: string;
  content: string; // Raw markdown text
  markdownContent: string;
  htmlContent?: string;
  sources: string[];
  tool: string;
  createdAt: string;
  wordCount?: number;
  type?: 'markdown' | 'html' | string;
}

export interface ChatMessageItem {
  id: string | number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  timestamp?: string;
  selected_tool?: string;
  sources?: string[];
  isArtifact?: boolean;
  isOptimistic?: boolean;
}

export interface ToastMessage {
  id: string;
  type: "success" | "error" | "info";
  message: string;
  duration?: number;
}
