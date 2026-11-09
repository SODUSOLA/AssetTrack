import { QueryClient } from "@tanstack/react-query";
import { isApiError } from "@/api/errors";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        // A 4xx will not improve by asking again; a dropped connection might.
        retry: (count, error) => !(isApiError(error) && error.status >= 400) && count < 2,
      },
      mutations: { retry: false },
    },
  });
}
