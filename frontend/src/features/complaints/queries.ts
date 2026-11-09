import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { ComplaintCreate, ComplaintStatus, ComplaintUpdate, PriorityLevel } from "@/api/types";
import { invalidateAfterEvent } from "@/features/devices/queries";

export const COMPLAINTS_PAGE_SIZE = 20;

export type ComplaintListParams = {
  page: number;
  status?: ComplaintStatus;
  priority?: PriorityLevel;
  unit_id?: string;
  assigned_to?: string;
  device_id?: string;
  date_from?: string;
  date_to?: string;
  page_size?: number;
};

export const complaintKeys = {
  list: (params: ComplaintListParams) => ["complaints", "list", params] as const,
  detail: (id: string) => ["complaints", "detail", id] as const,
};

export function useComplaints(params: ComplaintListParams, enabled = true) {
  const { page_size = COMPLAINTS_PAGE_SIZE, ...rest } = params;
  return useQuery({
    queryKey: complaintKeys.list(params),
    enabled,
    queryFn: ({ signal }) =>
      unwrap(api.GET("/api/v1/complaints", { params: { query: { ...rest, page_size } }, signal })),
    placeholderData: keepPreviousData,
  });
}

export function useComplaint(id: string) {
  return useQuery({
    queryKey: complaintKeys.detail(id),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET("/api/v1/complaints/{complaint_id}", {
          params: { path: { complaint_id: id } },
          signal,
        }),
      ),
  });
}

/** A change to a ticket can change its device, the work queues and the reports as well. */
function refresh(queryClient: QueryClient): Promise<unknown> {
  return invalidateAfterEvent(queryClient);
}

export function useRaiseComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ComplaintCreate) => unwrap(api.POST("/api/v1/complaints", { body })),
    onSettled: () => refresh(queryClient),
  });
}

export function useUpdateComplaint(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ComplaintUpdate) =>
      unwrap(
        api.PATCH("/api/v1/complaints/{complaint_id}", {
          params: { path: { complaint_id: id } },
          body,
        }),
      ),
    // Even a refused move means the page is out of date.
    onSettled: () => refresh(queryClient),
  });
}

export function useAddComment(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) =>
      unwrap(
        api.POST("/api/v1/complaints/{complaint_id}/comments", {
          params: { path: { complaint_id: id } },
          body: { body },
        }),
      ),
    onSettled: () => refresh(queryClient),
  });
}

export function useConfirmComplaint(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/complaints/{complaint_id}/confirm", {
          params: { path: { complaint_id: id } },
        }),
      ),
    onSettled: () => refresh(queryClient),
  });
}

export function useReopenComplaint(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) =>
      unwrap(
        api.POST("/api/v1/complaints/{complaint_id}/reopen", {
          params: { path: { complaint_id: id } },
          body: { reason },
        }),
      ),
    onSettled: () => refresh(queryClient),
  });
}
