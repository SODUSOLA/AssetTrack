import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { DeviceStatus, EventBody } from "@/api/types";
import type { components } from "@/api/schema";

export const DEVICES_PAGE_SIZE = 20;

export type DeviceListParams = {
  page: number;
  q?: string;
  status?: DeviceStatus;
  device_type?: string;
  unit_id?: string;
  page_size?: number;
};

export type DateRange = { from?: string; to?: string };

export const deviceKeys = {
  all: ["devices"] as const,
  list: (params: DeviceListParams) => ["devices", "list", params] as const,
  detail: (id: string) => ["devices", "detail", id] as const,
  timeline: (id: string, range: DateRange) => ["devices", "timeline", id, range] as const,
};

export function useDevices(params: DeviceListParams, enabled = true) {
  const { page_size = DEVICES_PAGE_SIZE, ...rest } = params;
  return useQuery({
    enabled,
    queryKey: deviceKeys.list(params),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET("/api/v1/devices", {
          params: { query: { ...rest, page_size } },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useDevice(id: string) {
  return useQuery({
    queryKey: deviceKeys.detail(id),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET("/api/v1/devices/{device_id}", { params: { path: { device_id: id } }, signal }),
      ),
  });
}

export function useTimeline(id: string, range: DateRange) {
  return useQuery({
    queryKey: deviceKeys.timeline(id, range),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET("/api/v1/devices/{device_id}/timeline", {
          params: {
            path: { device_id: id },
            query: { date_from: range.from, date_to: range.to },
          },
          signal,
        }),
      ),
  });
}

/** Everything that can change after an event: the device, the logs, the work queues and the reports. */
export function invalidateAfterEvent(queryClient: QueryClient): Promise<unknown> {
  return Promise.all(
    ["devices", "events", "acknowledgements", "complaints", "reports"].map((key) =>
      queryClient.invalidateQueries({ queryKey: [key] }),
    ),
  );
}

type DeviceCreate = components["schemas"]["DeviceCreate"];
type DeviceUpdate = components["schemas"]["DeviceUpdate"];

export function useRegisterDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DeviceCreate) => unwrap(api.POST("/api/v1/devices", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: deviceKeys.all }),
  });
}

export function useUpdateDevice(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DeviceUpdate) =>
      unwrap(
        api.PATCH("/api/v1/devices/{device_id}", { params: { path: { device_id: id } }, body }),
      ),
    onSuccess: () => invalidateAfterEvent(queryClient), // a correction is logged as an event
  });
}

export function useLogEvent(deviceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: EventBody) =>
      unwrap(
        api.POST("/api/v1/devices/{device_id}/events", {
          params: { path: { device_id: deviceId } },
          body,
        }),
      ),
    // Even a refused event (the device moved on) means the page is out of date.
    onSettled: () => invalidateAfterEvent(queryClient),
  });
}

/**
 * Tickets a device can be received for: open ones in the device's unit that are about this device
 * or about no device yet. Three small queries because the API filters by one status at a time.
 */
export function useIntakeTickets(
  unitId: string | null | undefined,
  deviceId: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["complaints", "intake", unitId, deviceId],
    enabled: enabled && !!unitId,
    queryFn: async ({ signal }) => {
      const statuses = ["open", "in_progress", "reopened"] as const;
      const pages = await Promise.all(
        statuses.map((status) =>
          unwrap(
            api.GET("/api/v1/complaints", {
              params: { query: { unit_id: unitId ?? undefined, status, page_size: 100 } },
              signal,
            }),
          ),
        ),
      );
      return pages
        .flatMap((page) => page.items)
        .filter((t) => !t.device || t.device.id === deviceId);
    },
  });
}
