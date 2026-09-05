import { useState, useCallback, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { SessionDetailResponse, ChatResponse } from '@/types/api';
import type { ChatMessageItem, ArtifactData } from '@/types/chat';
import { isShip30Artifact, extractArtifactTitle, countWords } from '@/lib/utils';

interface UseChatProps {
  sessionId: string | null;
  onArtifactDetected?: (artifact: ArtifactData) => void;
}

export function useChat({ sessionId, onArtifactDetected }: UseChatProps) {
  const queryClient = useQueryClient();
  const [optimisticMessages, setOptimisticMessages] = useState<ChatMessageItem[]>([]);

  // Fetch session details and history
  const sessionQuery = useQuery<SessionDetailResponse, Error>({
    queryKey: ['session', sessionId],
    queryFn: () => {
      if (!sessionId) throw new Error('No session ID provided');
      return api.getSessionDetails(sessionId);
    },
    enabled: !!sessionId,
    staleTime: 1000 * 30,
  });

  // Clear optimistic messages once session query data updates
  useEffect(() => {
    if (sessionQuery.data) {
      setOptimisticMessages([]);
    }
  }, [sessionQuery.data]);

  // Transform backend messages to UI messages
  const backendMessages: ChatMessageItem[] = (sessionQuery.data?.messages ?? []).map((msg) => ({
    id: String(msg.id),
    role: msg.role,
    content: msg.content,
    created_at: msg.created_at,
    timestamp: msg.created_at,
  }));

  // Combine backend messages with any pending optimistic messages
  const allMessages = [...backendMessages, ...optimisticMessages];

  // Send message mutation
  const sendMutation = useMutation<ChatResponse, Error, { message: string; targetSessionId: string }>({
    mutationFn: ({ message, targetSessionId }) =>
      api.sendMessage(targetSessionId, message),
    onMutate: async ({ message }) => {
      // Optimistically add user message
      const now = new Date().toISOString();
      const optimisticUserMsg: ChatMessageItem = {
        id: `optimistic-${Date.now()}`,
        role: 'user',
        content: message,
        created_at: now,
        timestamp: now,
        isOptimistic: true,
      };
      setOptimisticMessages((prev) => [...prev, optimisticUserMsg]);
    },
    onSuccess: (data, variables) => {
      // Invalidate the session query and the sessions list
      queryClient.invalidateQueries({ queryKey: ['session', variables.targetSessionId] });
      queryClient.invalidateQueries({ queryKey: ['sessions'] });

      // Check if the response is an artifact (Ship30 essay or large structured content)
      const isArtifact = data.artifact || isShip30Artifact(data.answer, data.selected_tool);
      if (isArtifact) {
        const mdText = data.markdown_content || data.answer;
        const title = extractArtifactTitle(mdText);
        const artifact: ArtifactData = {
          id: `artifact-${Date.now()}`,
          title,
          content: mdText,
          markdownContent: mdText,
          htmlContent: data.html_content,
          tool: data.selected_tool ?? 'Ship30Tool',
          sources: data.sources ?? [],
          createdAt: new Date().toISOString(),
          wordCount: data.word_count ?? countWords(mdText),
        };
        onArtifactDetected?.(artifact);
      }
    },
    onError: () => {
      // Remove optimistic message if send failed
      setOptimisticMessages([]);
    },
  });

  const sendMessage = useCallback(
    async (message: string, activeSessionId?: string) => {
      const idToUse = activeSessionId || sessionId;
      if (!idToUse) {
        throw new Error('No active session. Please create or select a session first.');
      }
      return sendMutation.mutateAsync({ message, targetSessionId: idToUse });
    },
    [sessionId, sendMutation]
  );

  return {
    messages: allMessages,
    isLoadingHistory: sessionQuery.isLoading,
    isSending: sendMutation.isPending,
    sendError: sendMutation.error,
    sessionTitle: sessionQuery.data?.title,
    sendMessage,
    refetchHistory: sessionQuery.refetch,
  };
}
