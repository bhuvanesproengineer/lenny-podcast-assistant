'use client';

import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { Badge } from '@/components/UI/Badge';
import { Button } from '@/components/UI/Button';
import { CitationsList } from '@/components/Chat/CitationsList';
import { formatRelativeTime, isShip30Artifact, extractArtifactTitle, countWords } from '@/lib/utils';
import type { ChatMessageItem, ArtifactData } from '@/types/chat';
import {
  Sparkles,
  User,
  FileText,
  Radio,
  Copy,
  Check,
  ArrowUpRight,
  Clock,
  BookOpen,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface ChatMessageProps {
  message: ChatMessageItem;
  onOpenArtifact?: (artifact: ArtifactData) => void;
  onCopyText?: (text: string) => void;
}

export function ChatMessage({
  message,
  onOpenArtifact,
  onCopyText,
}: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';
  const isArtifact = !isUser && isShip30Artifact(message.content, message.selected_tool);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    onCopyText?.(message.content);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleOpenArtifact = () => {
    if (onOpenArtifact) {
      const title = extractArtifactTitle(message.content);
      const artifact: ArtifactData = {
        id: `artifact-${message.id}`,
        title,
        content: message.content,
        markdownContent: message.content,
        tool: message.selected_tool ?? 'Ship30Tool',
        sources: message.sources ?? [],
        createdAt: message.created_at || message.timestamp || new Date().toISOString(),
        wordCount: countWords(message.content),
      };
      onOpenArtifact(artifact);
    }
  };

  const displayTime = formatRelativeTime(message.created_at || message.timestamp);
  const artifactTitle = useMemo(() => extractArtifactTitle(message.content), [message.content]);
  const words = useMemo(() => countWords(message.content), [message.content]);
  const readingMinutes = Math.max(1, Math.round(words / 200));

  // Extract a 2-3 line preview snippet for the article card
  const previewSnippet = useMemo(() => {
    if (!isArtifact) return '';
    const hookMatch = message.content.match(/##\s*Hook\s*\n+([\s\S]*?)(?=\n##|$)/i);
    if (hookMatch && hookMatch[1].trim()) {
      const clean = hookMatch[1].replace(/[*_#`]/g, '').trim();
      return clean.slice(0, 200) + (clean.length > 200 ? '...' : '');
    }
    const lines = message.content
      .split('\n')
      .filter((l) => !l.startsWith('#') && l.trim().length > 0);
    if (lines.length > 0) {
      const clean = lines[0].replace(/[*_#`]/g, '').trim();
      return clean.slice(0, 200) + (clean.length > 200 ? '...' : '');
    }
    return 'Actionable growth strategy and insights distilled from Lenny’s Podcast transcripts.';
  }, [message.content, isArtifact]);

  // USER MESSAGE: Right aligned, accent blue bubble
  if (isUser) {
    return (
      <div className="w-full py-2.5 px-4 md:px-8 flex justify-end group">
        <div className="flex items-end gap-2.5 max-w-[85%] md:max-w-[70%]">
          {/* Action on hover */}
          <button
            onClick={handleCopy}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-[#9CA3AF] hover:text-[#F3F4F6] rounded cursor-pointer mb-1"
            title="Copy message"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>

          {/* User Bubble */}
          <div className="flex flex-col items-end">
            <div className="bg-[#3B82F6] text-[#F3F4F6] px-4 py-3 rounded-2xl rounded-br-sm shadow-md shadow-blue-900/20 text-sm leading-relaxed whitespace-pre-wrap break-words">
              {message.content}
            </div>
            <span className="text-[10px] text-[#9CA3AF]/60 mt-1 px-1">
              {displayTime}
            </span>
          </div>

          {/* User Avatar */}
          <div className="w-7 h-7 rounded-full bg-[#212121] border border-[#2A2A2A] flex items-center justify-center text-[#9CA3AF] shrink-0 mb-5">
            <User className="w-3.5 h-3.5" />
          </div>
        </div>
      </div>
    );
  }

  // ASSISTANT MESSAGE: Left aligned, dark gray card bubble
  return (
    <div className="w-full py-3 px-4 md:px-8 flex justify-start group">
      <div className="flex items-start gap-3 max-w-[95%] md:max-w-[85%] lg:max-w-[80%]">
        {/* Assistant Avatar */}
        <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-blue-600 to-[#3B82F6] flex items-center justify-center text-white shadow-sm shadow-blue-500/30 shrink-0 mt-1">
          <Sparkles className="w-3.5 h-3.5" />
        </div>

        {/* Message Content Container */}
        <div className="flex-1 min-w-0 flex flex-col">
          {/* Header Bar */}
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-xs font-semibold text-[#F3F4F6]">
              Lenny Assistant
            </span>

            {/* Selected Tool Pill */}
            {message.selected_tool && (
              <Badge variant="tool" size="sm">
                {message.selected_tool === 'Ship30Tool' ? (
                  <>
                    <FileText className="w-3 h-3 text-[#60A5FA]" />
                    Ship30 Essay
                  </>
                ) : (
                  <>
                    <Radio className="w-3 h-3 text-emerald-400" />
                    Podcast RAG
                  </>
                )}
              </Badge>
            )}

            <span className="text-[11px] text-[#9CA3AF]/60 ml-auto">
              {displayTime}
            </span>

            <button
              onClick={handleCopy}
              className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-[#9CA3AF] hover:text-[#F3F4F6] rounded cursor-pointer"
              title="Copy response"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>
          </div>

          {/* Bubble / Card Body */}
          {isArtifact ? (
            /* ARTICLE GENERATION UX: Concise Card with Title, 2-3 line preview, Word Count, Read Time, and View Article button. No in-chat expansion! */
            <div className="w-full rounded-2xl rounded-tl-sm bg-[#212121] border border-[#2A2A2A] hover:border-[#3B82F6]/50 transition-all p-4 md:p-5 shadow-lg shadow-black/30 space-y-3.5">
              {/* Top metadata row */}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-md bg-[#3B82F6]/15 border border-[#3B82F6]/30 flex items-center justify-center text-[#60A5FA]">
                    <BookOpen className="w-3.5 h-3.5" />
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-[#60A5FA]">
                    Growth Article Ready
                  </span>
                </div>

                <div className="flex items-center gap-2 text-xs text-[#9CA3AF]">
                  <span className="px-2 py-0.5 rounded-md bg-[#171717] border border-[#2A2A2A] font-mono text-[11px] text-[#F3F4F6]">
                    {words.toLocaleString()} words
                  </span>
                  <span className="flex items-center gap-1 text-[11px]">
                    <Clock className="w-3 h-3 text-[#9CA3AF]" />
                    ~{readingMinutes} min read
                  </span>
                </div>
              </div>

              {/* Title & Preview */}
              <div>
                <h3 className="text-base md:text-lg font-bold text-[#F3F4F6] tracking-tight leading-snug">
                  {artifactTitle}
                </h3>
                <p className="text-xs text-[#9CA3AF] mt-1.5 italic line-clamp-3 leading-relaxed">
                  "{previewSnippet}"
                </p>
              </div>

              {/* Bottom Action Bar: Prominent "View Article" Button */}
              <div className="pt-2 border-t border-[#2A2A2A] flex items-center justify-between">
                <span className="text-[11px] text-[#9CA3AF]">
                  Full formatted essay opens in Artifact Viewer
                </span>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleOpenArtifact}
                  rightIcon={<ArrowUpRight className="w-3.5 h-3.5" />}
                  className="text-xs py-1.5 px-3.5 bg-[#3B82F6] hover:bg-[#60A5FA] text-[#F3F4F6] rounded-lg shadow-sm shadow-blue-500/20 font-medium"
                >
                  View Article
                </Button>
              </div>
            </div>
          ) : (
            /* STANDARD ASSISTANT RESPONSE BUBBLE */
            <div className="rounded-2xl rounded-tl-sm bg-[#212121] border border-[#2A2A2A] p-4 text-sm text-[#F3F4F6] leading-relaxed break-words shadow-sm">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
                components={{
                  h1: ({ children }) => (
                    <h1 className="text-lg font-bold text-[#F3F4F6] mt-3 mb-2 pb-1 border-b border-[#2A2A2A]">
                      {children}
                    </h1>
                  ),
                  h2: ({ children }) => (
                    <h2 className="text-base font-semibold text-[#F3F4F6] mt-3 mb-1.5">
                      {children}
                    </h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="text-sm font-semibold text-[#60A5FA] mt-2 mb-1">
                      {children}
                    </h3>
                  ),
                  p: ({ children }) => (
                    <p className="mb-2.5 last:mb-0 leading-relaxed text-[#F3F4F6]">
                      {children}
                    </p>
                  ),
                  ul: ({ children }) => (
                    <ul className="list-disc pl-5 mb-2.5 space-y-1 text-[#F3F4F6]">
                      {children}
                    </ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="list-decimal pl-5 mb-2.5 space-y-1 text-[#F3F4F6]">
                      {children}
                    </ol>
                  ),
                  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-2 border-[#3B82F6] pl-3 italic my-2.5 text-[#9CA3AF] bg-[#171717] py-1 rounded-r text-xs">
                      {children}
                    </blockquote>
                  ),
                  code: ({ className, children, ...props }) => {
                    const match = /language-(\w+)/.exec(className || '');
                    return match ? (
                      <code
                        className={cn(
                          'block p-3 rounded-xl bg-[#0F0F0F] font-mono text-xs overflow-x-auto border border-[#2A2A2A] text-blue-200 my-2',
                          className
                        )}
                        {...props}
                      >
                        {children}
                      </code>
                    ) : (
                      <code
                        className="px-1.5 py-0.5 rounded bg-[#171717] font-mono text-xs text-[#60A5FA] border border-[#2A2A2A]"
                        {...props}
                      >
                        {children}
                      </code>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>

              {/* Citations List if present */}
              {message.sources && message.sources.length > 0 && (
                <CitationsList sources={message.sources} />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
