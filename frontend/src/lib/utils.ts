import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Combines class names with Tailwind Merge for conflict-free utility classes.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Formats ISO timestamp to human-friendly relative time or date.
 */
export function formatRelativeTime(dateString?: string): string {
  if (!dateString) return "";
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return "";

    const now = new Date();
    const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffSeconds < 60) return "Just now";
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
    if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
    if (diffSeconds < 172800) return "Yesterday";
    if (diffSeconds < 604800) return `${Math.floor(diffSeconds / 86400)}d ago`;

    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch {
    return "";
  }
}

/**
 * Calculates word count of a given text.
 */
export function countWords(text: string): number {
  if (!text) return 0;
  return text.trim().split(/\s+/).filter(Boolean).length;
}

/**
 * Extracts a clean title from markdown headings (# or ##) or falls back.
 */
export function extractArtifactTitle(markdown: string, fallback = "Ship30 Essay"): string {
  if (!markdown) return fallback;
  const match = markdown.match(/^#+\s+(.*)$/m);
  if (match && match[1]) {
    return match[1].replace(/[*_~`]/g, "").trim();
  }
  return fallback;
}

/**
 * Determines whether a message represents a Ship30 / long-form artifact.
 * Supports both function signatures:
 *   isShip30Artifact(content, tool)
 *   isShip30Artifact({ selected_tool, content })
 */
export function isShip30Artifact(
  arg: string | { selected_tool?: string; content?: string },
  toolParam?: string
): boolean {
  const content = typeof arg === "string" ? arg : arg.content || "";
  const tool = typeof arg === "string" ? toolParam : arg.selected_tool;

  // Insufficient transcript evidence is never treated as a Ship30 artifact
  if (content.toLowerCase().includes("not enough transcript evidence available")) {
    return false;
  }

  if (tool === "Ship30Tool") {
    return true;
  }
  if (content) {
    const words = countWords(content);
    const hasHeaders = /^##?\s+/m.test(content);
    const hasSources = /###?\s*Sources/i.test(content) || content.includes("## Sources");
    if (words > 250 && hasHeaders && (hasSources || words > 500)) {
      return true;
    }
  }
  return false;
}

export type ArtifactType = "markdown" | "html";

/**
 * Automatically detects whether an artifact is an HTML/CSS document or Markdown (e.g. Ship 30 essay).
 * Returns 'html' or 'markdown'.
 */
export function detectArtifactType(artifact?: {
  tool?: string;
  content?: string;
  markdownContent?: string;
  htmlContent?: string;
  type?: string;
} | null): ArtifactType {
  if (!artifact) return "markdown";

  // 1. Explicit type field if specified
  if (artifact.type === "html") return "html";
  if (artifact.type === "markdown") return "markdown";

  // 2. Explicit tool name indicators
  const toolLower = (artifact.tool || "").toLowerCase();
  if (toolLower.includes("html") || toolLower.includes("css") || toolLower.includes("web")) {
    return "html";
  }
  if (toolLower.includes("ship30") || toolLower.includes("essay")) {
    return "markdown";
  }

  // 3. Inspect content text
  const text = (artifact.markdownContent || artifact.content || "").trim();

  // 4. Code block fence check (e.g. ```html or ```css at start of content)
  if (/^```(?:html|htm|css)\b/i.test(text)) {
    return "html";
  }

  // 5. HTML Document doctype or root tag
  if (/^<!DOCTYPE\s+html/i.test(text) || /^<html[\s>]/i.test(text)) {
    return "html";
  }

  // 6. Check for dominant HTML structure (<style>, <script>, <div>, etc.) vs Markdown headers
  const hasStyleOrScript = /<(?:style|script)\b[^>]*>/i.test(text);
  const hasClosingTags = /<\/(?:div|span|p|style|script|section|header|footer|nav|main|article|table|ul|ol|form|button)>/i.test(text);
  const hasMarkdownHeaders = /^#{1,6}\s+\S+/m.test(text);

  if ((hasStyleOrScript || hasClosingTags) && !hasMarkdownHeaders) {
    return "html";
  }

  // 7. If htmlContent is explicitly provided and there is no markdown content, treat as html
  if (artifact.htmlContent && !text) {
    return "html";
  }

  // Default to markdown (Ship 30 essays, long-form guides, notes)
  return "markdown";
}

/**
 * Retrieves the raw content to export, preserving all original content and formatting.
 * For HTML artifacts wrapped in markdown code fences, unescapes the code fence to yield clean HTML.
 */
export function getArtifactExportContent(
  artifact: {
    content?: string;
    markdownContent?: string;
    htmlContent?: string;
  },
  type: ArtifactType
): string {
  const rawText = artifact.markdownContent || artifact.content || "";

  if (type === "html") {
    // If the content is wrapped in ```html ... ``` or ```css ... ``` code block, extract inner code
    const codeBlockMatch = rawText.match(/^```(?:html|htm|css)?\s*\n([\s\S]*?)\n```\s*$/i);
    if (codeBlockMatch && codeBlockMatch[1]) {
      return codeBlockMatch[1].trim();
    }
    // If explicit htmlContent was provided and rawText doesn't look like HTML
    if (artifact.htmlContent && !rawText.includes("<html") && !rawText.includes("<!DOCTYPE") && !rawText.includes("<div")) {
      return artifact.htmlContent;
    }
    return rawText;
  }

  // For markdown, preserve all text and formatting as-is
  return rawText;
}
