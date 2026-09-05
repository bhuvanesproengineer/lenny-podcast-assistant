import React, { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/UI/Button';
import { Send, Sparkles, CornerDownLeft, Loader2 } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, isLoading, disabled }: ChatInputProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-resize textarea as text grows
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        200
      )}px`;
    }
  }, [text]);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || isLoading || disabled) return;
    onSend(trimmed);
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-[#2A2A2A] bg-[#0F0F0F]/95 backdrop-blur px-4 py-3 md:px-8">
      <form onSubmit={handleSubmit} className="relative max-w-4xl mx-auto">
        <div className="relative flex items-end rounded-2xl bg-[#212121] border border-[#2A2A2A] focus-within:border-[#3B82F6] focus-within:ring-1 focus-within:ring-[#3B82F6]/30 transition-all p-2 shadow-lg shadow-black/40">
          <textarea
            ref={textareaRef}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled || isLoading}
            placeholder="Ask about product strategy, growth frameworks, or request a Ship30 essay..."
            className="w-full resize-none bg-transparent px-3 py-2 text-sm text-[#F3F4F6] placeholder-[#9CA3AF]/60 focus:outline-none max-h-48 leading-relaxed disabled:opacity-50"
          />

          <div className="shrink-0 pb-0.5 pr-0.5">
            <Button
              type="submit"
              size="icon"
              variant="primary"
              disabled={!text.trim() || isLoading || disabled}
              className="h-8 w-8 rounded-xl bg-[#3B82F6] hover:bg-[#60A5FA] text-[#F3F4F6] shadow-sm transition-transform active:scale-95 disabled:bg-[#2A2A2A] disabled:text-[#9CA3AF]/40"
              title="Send message (Enter)"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin text-white" />
              ) : (
                <Send className="w-3.5 h-3.5 text-white" />
              )}
            </Button>
          </div>
        </div>

        <div className="flex items-center justify-between text-[11px] text-[#9CA3AF] mt-2 px-1">
          <span className="hidden sm:inline">
            Press <kbd className="px-1.5 py-0.5 rounded bg-[#171717] border border-[#2A2A2A] font-mono text-[10px] text-[#9CA3AF]">Enter</kbd> to send, <kbd className="px-1.5 py-0.5 rounded bg-[#171717] border border-[#2A2A2A] font-mono text-[10px] text-[#9CA3AF]">Shift + Enter</kbd> for newline
          </span>
          <span className="text-[11px] text-[#9CA3AF] flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-[#3B82F6]" />
            Podcast RAG & Ship30 Agent
          </span>
        </div>
      </form>
    </div>
  );
}
