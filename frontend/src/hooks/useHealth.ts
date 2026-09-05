import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { HealthResponse } from '@/types/api';

export function useHealth() {
  return useQuery<HealthResponse, Error>({
    queryKey: ['health'],
    queryFn: () => api.getHealth(),
    refetchInterval: 30000, // Poll every 30s
    retry: 2,
    staleTime: 15000,
  });
}
