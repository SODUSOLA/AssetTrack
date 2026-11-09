import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { AckStatus } from "@/api/types";
import { invalidateAfterEvent } from "@/features/devices/queries";

export const ACKS_PAGE_SIZE = 20;

export type PendingParams = {
  page: number;
  unit_id?: string;
  overdue?: boolean;
  page_size?: number;
};

export function usePendingAcknowledgements(params: PendingParams) {
  const { page_size = ACKS_PAGE_SIZE, ...rest } = params;
  return useQuery({
    queryKey: ["acknowledgements", "pending", params],
    queryFn: ({ signal }) =>
      unwrap(
        api.GET("/api/v1/acknowledgements/pending", {
          params: { query: { ...rest, page_size } },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useAcknowledge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { eventId: number; status: AckStatus; comment?: string }) =>
      unwrap(
        api.POST("/api/v1/events/{event_id}/acknowledge", {
          params: { path: { event_id: input.eventId } },
          body: { status: input.status, comment: input.comment ?? null },
        }),
      ),
    onSettled: () => invalidateAfterEvent(queryClient),
  });
}
