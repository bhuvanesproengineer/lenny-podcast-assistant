import React from 'react';
import { Sparkles, Radio, FileText, Compass, ArrowRight } from 'lucide-react';

interface EmptyStateProps {
  onSelectPrompt: (prompt: string) => void;
}

const STARTER_PROMPTS = [
  {
    title: 'Podcast RAG',
    desc: 'How should product teams prioritize features according to podcast guests?',
    prompt: 'How should product teams prioritize features?',
    icon: <Radio className="w-4 h-4 text-emerald-400" />,
    badge: 'PodcastRAGTool',
  },
  {
    title: 'Ship30 Essay',
    desc: 'Write a full Ship 30 for 30 essay on product strategy and retention loops.',
    prompt: 'Write a Ship30 article about product strategy',
    icon: <FileText className="w-4 h-4 text-amber-400" />,
    badge: 'Ship30Tool',
  },
  {
    title: 'Podcast RAG',
    desc: 'What are the most common growth pitfalls in early-stage SaaS startups?',
    prompt: 'What are the most common growth pitfalls in early-stage SaaS startups?',
    icon: <Radio className="w-4 h-4 text-emerald-400" />,
    badge: 'PodcastRAGTool',
  },
  {
    title: 'Ship30 Essay',
    desc: 'Draft a 1,250-word Ship30 article on PM prioritization frameworks with hook and rhythm.',
    prompt: 'Write a Ship30 article on PM prioritization frameworks',
    icon: <FileText className="w-4 h-4 text-amber-400" />,
    badge: 'Ship30Tool',
  },
];

export function EmptyState({ onSelectPrompt }: EmptyStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 text-center max-w-2xl mx-auto my-auto select-none">
      <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-blue-600 to-[#3B82F6] flex items-center justify-center text-white shadow-lg shadow-blue-500/25 mb-4 animate-in zoom-in-75 duration-300">
        <Sparkles className="w-6 h-6 text-white" />
      </div>

      <h2 className="text-xl font-bold text-[#F3F4F6] tracking-tight">
        Lenny Growth Assistant
      </h2>
      <p className="text-sm text-[#9CA3AF] mt-1.5 max-w-md leading-relaxed">
        Ask product strategy and framework questions from Lenny's podcast transcripts, or synthesize long-form Ship 30 for 30 essays.
      </p>

      {/* Starter Prompts Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full mt-8 text-left">
        {STARTER_PROMPTS.map((item, idx) => (
          <button
            key={idx}
            onClick={() => onSelectPrompt(item.prompt)}
            className="p-3.5 rounded-xl bg-[#212121] hover:bg-[#262626] border border-[#2A2A2A] hover:border-[#3B82F6]/50 transition-all duration-200 group flex flex-col justify-between cursor-pointer shadow-sm hover:shadow-md"
          >
            <div>
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-[#F3F4F6]">
                  {item.icon}
                  <span>{item.title}</span>
                </div>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#171717] text-[#9CA3AF] border border-[#2A2A2A]">
                  {item.badge}
                </span>
              </div>
              <p className="text-xs text-[#9CA3AF] group-hover:text-[#F3F4F6]/90 transition-colors line-clamp-2 leading-relaxed">
                {item.desc}
              </p>
            </div>
            <div className="flex items-center text-[11px] text-[#60A5FA] group-hover:text-[#3B82F6] font-medium mt-3 gap-1">
              <span>Ask now</span>
              <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
