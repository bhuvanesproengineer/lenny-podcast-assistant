import React, { useRef, useEffect } from 'react';
import { ChatMessage } from '@/components/Chat/ChatMessage';
import { ChatInput } from '@/components/Chat/ChatInput';
import { EmptyState } from '@/components/Chat/EmptyState';
import { Sparkles, Loader2, AlertCircle } from 'lucide-react';
import type { ChatMessageItem, ArtifactData } from '@/types/chat';

interface ChatPanelProps {
  messages: ChatMessageItem[];
  isLoadingHistory: boolean;
  isSending: boolean;
  sendError: Error | null;
  sessionTitle?: string;
  onSendMessage: (message: string) => void;
  onOpenArtifact?: (artifact: ArtifactData) => void;
  onCopyText?: (text: string) => void;
}

export function ChatPanel({
  messages,
  isLoadingHistory,
  isSending,
  sendError,
  sessionTitle,
  onSendMessage,
  onOpenArtifact,
  onCopyText,
}: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom on new messages or loading state
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isSending]);

  return (
    <div className="flex-1 flex flex-col h-full bg-[#0F0F0F] relative min-w-0 overflow-hidden">
      {/* Session Title Bar */}
      {sessionTitle && (
        <div className="px-6 py-2.5 border-b border-[#2A2A2A] bg-[#0F0F0F]/80 backdrop-blur text-xs text-[#9CA3AF] flex items-center justify-between z-10 shrink-0">
          <span className="font-medium text-[#F3F4F6] truncate max-w-md">
            {sessionTitle}
          </span>
          <span className="text-[11px] text-[#9CA3AF]/70 font-mono">
            {messages.length} message{messages.length === 1 ? '' : 's'}
          </span>
        </div>
      )}

      {/* Messages Scroll Area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto py-4 flex flex-col space-y-1"
      >
        {isLoadingHistory ? (
          <div className="flex-1 flex flex-col items-center justify-center text-[#9CA3AF] gap-2">
            <Loader2 className="w-6 h-6 animate-spin text-[#3B82F6]" />
            <span className="text-sm">Loading conversation...</span>
          </div>
        ) : messages.length === 0 ? (
          <EmptyState onSelectPrompt={onSendMessage} />
        ) : (
          messages.map((message) => (
            <ChatMessage
              key={message.id}
              message={message}
              onOpenArtifact={onOpenArtifact}
              onCopyText={onCopyText}
            />
          ))
        )}

        {/* Pending Assistant Indicator */}
        {isSending && (
          <div className="w-full py-3 px-4 md:px-8 flex justify-start">
            <div className="flex items-center gap-3">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-blue-600 to-[#3B82F6] flex items-center justify-center text-white shadow-sm shadow-blue-500/30 shrink-0">
                <Sparkles className="w-3.5 h-3.5 animate-pulse" />
              </div>
              <div className="flex items-center gap-2 px-4 py-2.5 rounded-2xl rounded-tl-sm bg-[#212121] border border-[#2A2A2A] shadow-sm">
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3B82F6] animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3B82F6] animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3B82F6] animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span className="text-xs text-[#9CA3AF] font-medium ml-1">
                  Lenny Assistant is reasoning...
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Error Banner */}
        {sendError && (
          <div className="mx-6 my-3 p-3 rounded-xl bg-red-950/30 border border-red-900/50 flex items-start gap-2.5 text-xs text-red-300">
            <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <span className="font-semibold text-red-200">Error: </span>
              <span>{sendError.message || 'Failed to send message. Please check backend connection.'}</span>
            </div>
          </div>
        )}
      </div>

      {/* Input Area */}
      <ChatInput
        onSend={onSendMessage}
        isLoading={isSending}
        disabled={isLoadingHistory}
      />
    </div>
  );
}
