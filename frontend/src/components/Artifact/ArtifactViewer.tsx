'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Tabs, TabItem } from '@/components/UI/Tabs';
import { Badge } from '@/components/UI/Badge';
import { Button } from '@/components/UI/Button';
import { MarkdownPreview } from '@/components/Artifact/MarkdownPreview';
import { HtmlSandbox } from '@/components/Artifact/HtmlSandbox';
import { CodeViewer } from '@/components/Artifact/CodeViewer';
import type { ArtifactData, ArtifactTab } from '@/types/chat';
import { api } from '@/lib/api';
import {
  X,
  Maximize2,
  Minimize2,
  Copy,
  Check,
  Download,
  Eye,
  FileCode,
  Code2,
  FileText,
  Loader2,
  ChevronDown,
} from 'lucide-react';
import { cn, detectArtifactType, getArtifactExportContent } from '@/lib/utils';

interface ArtifactViewerProps {
  artifact: ArtifactData | null;
  isOpen: boolean;
  onClose: () => void;
  className?: string;
}

export function ArtifactViewer({
  artifact,
  isOpen,
  onClose,
  className,
}: ArtifactViewerProps) {
  const [activeTab, setActiveTab] = useState<ArtifactTab>('preview');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [isExportingDocx, setIsExportingDocx] = useState(false);
  const [isExportingNative, setIsExportingNative] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        exportMenuRef.current &&
        !exportMenuRef.current.contains(event.target as Node)
      ) {
        setShowExportMenu(false);
      }
    }
    if (showExportMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [showExportMenu]);

  useEffect(() => {
    if (exportError) {
      const timer = setTimeout(() => setExportError(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [exportError]);

  if (!isOpen || !artifact) return null;

  const artifactType = detectArtifactType(artifact);
  const markdownText = artifact.markdownContent || artifact.content || '';
  const exportContent = getArtifactExportContent(artifact, artifactType);
  const wordCount = artifact.wordCount ?? (markdownText ? markdownText.trim().split(/\s+/).filter(Boolean).length : 0);
  const readingTime = Math.max(1, Math.ceil(wordCount / 225));

  const handleCopy = () => {
    const textToCopy =
      activeTab === 'html'
        ? artifact.htmlContent || markdownText
        : markdownText;

    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleExportPdf = async () => {
    try {
      setIsExportingPdf(true);
      setExportError(null);
      const textToExport = markdownText.trim() || exportContent.trim() || artifact.title;
      await api.downloadExport('pdf', textToExport, artifact.title);
    } catch (err: any) {
      console.error('Failed to download PDF:', err);
      setExportError(err?.message || 'Failed to export PDF. Please try again.');
    } finally {
      setIsExportingPdf(false);
    }
  };

  const handleExportDocx = async () => {
    try {
      setIsExportingDocx(true);
      setExportError(null);
      const textToExport = markdownText.trim() || exportContent.trim() || artifact.title;
      await api.downloadExport('docx', textToExport, artifact.title);
    } catch (err: any) {
      console.error('Failed to download Word document:', err);
      setExportError(err?.message || 'Failed to export Word document. Please try again.');
    } finally {
      setIsExportingDocx(false);
    }
  };

  const handleExportMarkdown = () => {
    try {
      setExportError(null);
      api.downloadMarkdown(markdownText || exportContent, artifact.title);
    } catch (err: any) {
      console.error('Failed to export markdown:', err);
      setExportError('Failed to export markdown file.');
    }
  };

  const handleExportHtml = () => {
    try {
      setExportError(null);
      const htmlContent = artifact.htmlContent || htmlDisplay;
      api.downloadHtml(htmlContent, artifact.title);
    } catch (err: any) {
      console.error('Failed to export HTML:', err);
      setExportError('Failed to export HTML file.');
    }
  };

  // Build basic HTML string if not provided
  const htmlDisplay =
    artifact.htmlContent ||
    `<!-- Generated from ${artifact.title} -->\n<article class="ship30-article">\n  <h1>${artifact.title}</h1>\n  <div class="content">\n${markdownText
      .split('\n\n')
      .map((p: string) => `    <p>${p.trim()}</p>`)
      .join('\n')}\n  </div>\n</article>`;

  const tabs: TabItem[] = [
    { id: 'preview', label: 'Preview', icon: <Eye className="w-3.5 h-3.5" /> },
    { id: 'markdown', label: 'Raw Markdown', icon: <FileCode className="w-3.5 h-3.5" /> },
    { id: 'html', label: 'Raw HTML', icon: <Code2 className="w-3.5 h-3.5" /> },
  ];

  return (
    <div
      className={cn(
        'bg-[#171717] border-l border-[#2A2A2A] flex flex-col h-full z-30 transition-all duration-200 shadow-2xl',
        isFullscreen
          ? 'fixed inset-0 w-screen h-screen z-50 border-0'
          : 'w-full md:w-[50%] lg:w-[46%] xl:w-[42%] shrink-0',
        className
      )}
    >
      {/* Sticky Top Header Bar */}
      <div className="sticky top-0 z-20 p-3.5 border-b border-[#2A2A2A] bg-[#171717]/95 backdrop-blur-md flex flex-col gap-3 shrink-0">
        {/* Title & Primary Actions Row */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-[#3B82F6]/15 border border-[#3B82F6]/30 flex items-center justify-center shrink-0">
              <FileText className="w-4 h-4 text-[#60A5FA]" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-[#F3F4F6] truncate leading-snug">
                {artifact.title}
              </h2>
              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                <Badge variant="tool" size="sm">
                  {artifact.tool || 'Ship30 Essay'}
                </Badge>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-[#212121] text-[#60A5FA] border border-[#2A2A2A] flex items-center gap-1 font-medium" title="Article word count">
                  {wordCount.toLocaleString()} words
                </span>
                <span className="text-[10px] text-[#9CA3AF]">
                  ~{readingTime} min read
                </span>
                <span className="text-[10px] text-[#9CA3AF]/40">•</span>
                <span className="text-[10px] text-[#9CA3AF]">
                  {new Date(artifact.createdAt).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </div>
            </div>
          </div>

          {/* Action buttons with PDF Export as Primary Default */}
          <div className="flex items-center gap-1.5 shrink-0">
            {/* Primary Action: PDF Export + Optional Dropdown */}
            <div className="relative inline-flex items-center rounded-md shadow-sm" ref={exportMenuRef}>
              <Button
                variant="primary"
                size="sm"
                onClick={handleExportPdf}
                disabled={isExportingPdf}
                leftIcon={
                  isExportingPdf ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-white" />
                  ) : (
                    <Download className="w-3.5 h-3.5 text-white" />
                  )
                }
                className="text-xs h-8 px-2.5 bg-[#3B82F6] hover:bg-[#60A5FA] text-[#F3F4F6] font-medium rounded-r-none border-r border-blue-400/30 shadow-sm shadow-blue-500/25"
                title="Download publication-ready PDF document (.pdf)"
              >
                {isExportingPdf ? 'Exporting PDF...' : 'Export (PDF)'}
              </Button>
              <button
                type="button"
                onClick={() => setShowExportMenu((prev) => !prev)}
                disabled={isExportingPdf || isExportingDocx || isExportingNative}
                className="h-8 px-1.5 bg-[#3B82F6] hover:bg-[#60A5FA] text-[#F3F4F6] rounded-r-md transition-colors cursor-pointer flex items-center justify-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3B82F6]/50 shadow-sm shadow-blue-500/25"
                title="Choose export format"
              >
                <ChevronDown
                  className={cn(
                    'w-3.5 h-3.5 transition-transform duration-150',
                    showExportMenu && 'rotate-180'
                  )}
                />
              </button>

              {/* Export Format Dropdown Menu */}
              {showExportMenu && (
                <div className="absolute right-0 top-full mt-1.5 w-56 rounded-lg bg-[#212121] border border-[#2A2A2A] shadow-xl py-1 z-50 animate-in fade-in zoom-in-95 duration-100">
                  <div className="px-3 py-1 text-[10px] uppercase font-semibold tracking-wider text-[#9CA3AF]/70 border-b border-[#2A2A2A]">
                    Export Formats
                  </div>
                  {/* PDF option (Default) */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowExportMenu(false);
                      handleExportPdf();
                    }}
                    disabled={isExportingPdf}
                    className="w-full text-left px-3 py-2 text-xs text-[#F3F4F6] hover:bg-[#2A2A2A] flex items-center justify-between transition-colors cursor-pointer"
                  >
                    <span className="flex items-center gap-2 font-medium">
                      {isExportingPdf ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-[#60A5FA]" />
                      ) : (
                        <FileText className="w-3.5 h-3.5 text-[#60A5FA]" />
                      )}
                      PDF (.pdf)
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#3B82F6]/20 text-[#60A5FA] font-medium">
                      Default
                    </span>
                  </button>

                  {/* Word DOCX option */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowExportMenu(false);
                      handleExportDocx();
                    }}
                    disabled={isExportingDocx}
                    className="w-full text-left px-3 py-2 text-xs text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#2A2A2A] flex items-center justify-between transition-colors cursor-pointer"
                  >
                    <span className="flex items-center gap-2">
                      {isExportingDocx ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-[#9CA3AF]" />
                      ) : (
                        <FileCode className="w-3.5 h-3.5 text-[#9CA3AF]" />
                      )}
                      Word (.docx)
                    </span>
                    <span className="text-[10px] text-[#9CA3AF]/60">
                      Document
                    </span>
                  </button>

                  {/* Markdown option */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowExportMenu(false);
                      handleExportMarkdown();
                    }}
                    className="w-full text-left px-3 py-2 text-xs text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#2A2A2A] flex items-center justify-between transition-colors cursor-pointer"
                  >
                    <span className="flex items-center gap-2">
                      <Download className="w-3.5 h-3.5 text-[#9CA3AF]" />
                      Markdown (.md)
                    </span>
                    <span className="text-[10px] text-[#9CA3AF]/60">
                      Markdown
                    </span>
                  </button>

                  {/* HTML option */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowExportMenu(false);
                      handleExportHtml();
                    }}
                    className="w-full text-left px-3 py-2 text-xs text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#2A2A2A] flex items-center justify-between transition-colors cursor-pointer"
                  >
                    <span className="flex items-center gap-2">
                      <Code2 className="w-3.5 h-3.5 text-[#9CA3AF]" />
                      HTML (.html)
                    </span>
                    <span className="text-[10px] text-[#9CA3AF]/60">
                      Web
                    </span>
                  </button>
                </div>
              )}
            </div>

            {/* Copy Button */}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopy}
              leftIcon={
                copied ? (
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )
              }
              className="text-xs h-8 px-2.5 text-[#9CA3AF] hover:text-[#F3F4F6]"
              title="Copy to clipboard"
            >
              {copied ? 'Copied' : 'Copy'}
            </Button>

            <div className="h-4 w-px bg-[#2A2A2A] mx-0.5" />

            {/* Fullscreen Toggle */}
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-1.5 text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#212121] rounded-lg transition-colors cursor-pointer"
              title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
            >
              {isFullscreen ? (
                <Minimize2 className="w-4 h-4" />
              ) : (
                <Maximize2 className="w-4 h-4" />
              )}
            </button>

            {/* Close Button */}
            <button
              onClick={onClose}
              className="p-1.5 text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#212121] rounded-lg transition-colors cursor-pointer"
              title="Close artifact"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center justify-between">
          <Tabs
            tabs={tabs}
            activeTab={activeTab}
            onChange={(tab) => setActiveTab(tab as ArtifactTab)}
          />
        </div>

        {exportError && (
          <div className="px-3 py-1.5 bg-red-500/10 border border-red-500/30 text-red-400 text-xs rounded-md flex items-center justify-between animate-in fade-in duration-150">
            <span>{exportError}</span>
            <button
              onClick={() => setExportError(null)}
              className="text-red-400 hover:text-red-200 ml-2"
              title="Dismiss error"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Tab Content Body with Independent Scrolling */}
      <div className="flex-1 overflow-y-auto min-h-0 bg-[#0F0F0F]">
        {activeTab === 'preview' && (
          <MarkdownPreview content={markdownText} />
        )}

        {activeTab === 'markdown' && (
          <CodeViewer code={markdownText} language="markdown" />
        )}

        {activeTab === 'html' && (
          <div className="h-full flex flex-col">
            <div className="h-1/2 border-b border-[#2A2A2A]">
              <HtmlSandbox htmlContent={htmlDisplay} />
            </div>
            <div className="h-1/2">
              <CodeViewer code={htmlDisplay} language="html" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

