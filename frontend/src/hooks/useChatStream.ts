import { useState, useCallback } from 'react';
import { api } from '@/lib/api';
import type { ChatResponse } from '@/types/api';

interface UseChatStreamOptions {
  sessionId: string | null;
  onChunk?: (chunk: string) => void;
  onFinish?: (response: ChatResponse) => void;
  onError?: (error: Error) => void;
}

export function useChatStream({
  sessionId,
  onChunk,
  onFinish,
  onError,
}: UseChatStreamOptions) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState('');

  const sendStreamMessage = useCallback(
    async (message: string, targetSessionId?: string) => {
      const activeId = targetSessionId || sessionId;
      if (!activeId) {
        throw new Error('No active session for streaming');
      }

      setIsStreaming(true);
      setStreamedText('');

      try {
        const response = await api.sendMessage(activeId, message);
        setStreamedText(response.answer);
        onChunk?.(response.answer);
        onFinish?.(response);
        return response;
      } catch (err: any) {
        const error = err instanceof Error ? err : new Error(String(err));
        onError?.(error);
        throw error;
      } finally {
        setIsStreaming(false);
      }
    },
    [sessionId, onChunk, onFinish, onError]
  );

  return {
    isStreaming,
    streamedText,
    sendStreamMessage,
  };
}
