'use client';

import React, { useState } from 'react';
import { Cpu, ChevronDown, Check, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ModelOption {
  id: string;
  name: string;
  provider: 'local' | 'cloud';
  description: string;
}

const AVAILABLE_MODELS: ModelOption[] = [
  {
    id: 'llama3.2:3b',
    name: 'Llama 3.2 (3B)',
    provider: 'local',
    description: 'Fast local reasoning & tool routing via Ollama',
  },
  {
    id: 'qwen3:4b',
    name: 'Qwen 3 (4B)',
    provider: 'local',
    description: 'Local reasoning & structured outputs via Ollama',
  },
  {
    id: 'gpt-4o',
    name: 'GPT-4o',
    provider: 'cloud',
    description: 'OpenAI high-intelligence cloud model',
  },
];

interface ModelSelectorProps {
  selectedModel?: string;
  onSelectModel?: (modelId: string) => void;
  className?: string;
}

export function ModelSelector({
  selectedModel = 'llama3.2:3b',
  onSelectModel,
  className,
}: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const current = AVAILABLE_MODELS.find((m) => m.id === selectedModel) || AVAILABLE_MODELS[0];

  return (
    <div className={cn('relative inline-block text-left', className)}>
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-card border border-surface-border text-xs text-slate-300 font-mono hover:border-slate-600 transition-colors focus:outline-none"
        aria-expanded={isOpen}
      >
        <Cpu className="w-3.5 h-3.5 text-amber-400" />
        <span>{current.name}</span>
        <ChevronDown className="w-3 h-3 text-slate-400" />
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-30"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 mt-2 w-64 rounded-xl bg-surface-card border border-surface-border shadow-xl z-40 p-1.5 backdrop-blur-md">
            <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-slate-400 font-mono">
              Inference Provider
            </div>
            {AVAILABLE_MODELS.map((model) => {
              const isSelected = model.id === current.id;
              return (
                <button
                  key={model.id}
                  onClick={() => {
                    onSelectModel?.(model.id);
                    setIsOpen(false);
                  }}
                  className={cn(
                    'w-full flex items-start gap-2 px-2.5 py-2 rounded-lg text-left text-xs transition-colors cursor-pointer',
                    isSelected
                      ? 'bg-amber-500/10 text-amber-300'
                      : 'text-slate-300 hover:bg-surface-elevated hover:text-slate-100'
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 font-medium">
                      <span>{model.name}</span>
                      <span className="text-[10px] px-1 py-0.2 rounded bg-surface-elevated text-slate-400 uppercase font-mono">
                        {model.provider}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-500 truncate mt-0.5">
                      {model.description}
                    </div>
                  </div>
                  {isSelected && <Check className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
