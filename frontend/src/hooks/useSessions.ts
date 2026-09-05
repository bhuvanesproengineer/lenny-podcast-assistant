import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { SessionSummaryResponse, CreateSessionResponse } from '@/types/api';

export function useSessions() {
  const queryClient = useQueryClient();

  const sessionsQuery = useQuery<SessionSummaryResponse[], Error>({
    queryKey: ['sessions'],
    queryFn: () => api.getSessions(0, 50),
    staleTime: 1000 * 60, // 1 minute
  });

  const createSessionMutation = useMutation<CreateSessionResponse, Error, string | undefined>({
    mutationFn: (title?: string) => api.createSession(title),
    onSuccess: (newSession) => {
      // Invalidate sessions list
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      return newSession;
    },
  });

  const renameSessionMutation = useMutation<SessionSummaryResponse, Error, { id: string; title: string }>({
    mutationFn: ({ id, title }) => api.renameSession(id, title),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      queryClient.invalidateQueries({ queryKey: ['session', updated.id] });
    },
  });

  const deleteSessionMutation = useMutation<void, Error, string>({
    mutationFn: (id: string) => api.deleteSession(id),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
      queryClient.removeQueries({ queryKey: ['session', deletedId] });
    },
  });

  return {
    sessions: sessionsQuery.data ?? [],
    isLoading: sessionsQuery.isLoading,
    isError: sessionsQuery.isError,
    error: sessionsQuery.error,
    refetchSessions: sessionsQuery.refetch,
    createSession: createSessionMutation.mutateAsync,
    isCreating: createSessionMutation.isPending,
    renameSession: renameSessionMutation.mutateAsync,
    isRenaming: renameSessionMutation.isPending,
    deleteSession: deleteSessionMutation.mutateAsync,
    isDeleting: deleteSessionMutation.isPending,
  };
}
