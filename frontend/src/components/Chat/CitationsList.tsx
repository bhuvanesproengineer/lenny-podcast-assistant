import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Radio, BookOpen, Quote } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CitationsListProps {
  sources: string[];
  className?: string;
}

export function CitationsList({ sources, className }: CitationsListProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!sources || sources.length === 0) return null;

  return (
    <div
      className={cn(
        'mt-3 border border-[#2A2A2A] bg-[#171717] rounded-xl overflow-hidden transition-all',
        className
      )}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#212121] transition-colors cursor-pointer"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-2">
          <Radio className="w-3.5 h-3.5 text-[#3B82F6] shrink-0" />
          <span className="font-medium text-[#F3F4F6]">
            Source Transcripts & Episodes ({sources.length})
          </span>
        </div>
        {isOpen ? (
          <ChevronUp className="w-3.5 h-3.5 text-[#9CA3AF]" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-[#9CA3AF]" />
        )}
      </button>

      {isOpen && (
        <div className="px-3 pb-3 pt-1 space-y-1.5 border-t border-[#2A2A2A]">
          {sources.map((source, index) => (
            <div
              key={index}
              className="flex items-start gap-2 p-2 rounded-lg bg-[#0F0F0F] border border-[#2A2A2A] text-xs text-[#9CA3AF] font-mono"
            >
              <Quote className="w-3.5 h-3.5 text-[#3B82F6] shrink-0 mt-0.5" />
              <span className="break-words leading-relaxed text-[#F3F4F6]/90">{source}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
