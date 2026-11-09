import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { Unit, UnitCreate, UnitUpdate } from "@/api/types";

const PAGE_SIZE = 100;

async function fetchAllUnits(signal: AbortSignal): Promise<Unit[]> {
  const units: Unit[] = [];
  for (let page = 1; ; page += 1) {
    const result = await unwrap(
      api.GET("/api/v1/units", { params: { query: { page, page_size: PAGE_SIZE } }, signal }),
    );
    units.push(...result.items);
    if (units.length >= result.total || result.items.length === 0) return units;
  }
}

/** Every unit, for pickers. There are few units, so one cached list serves the whole app. */
export function useUnits(enabled = true) {
  return useQuery({
    queryKey: ["units"],
    queryFn: ({ signal }) => fetchAllUnits(signal),
    staleTime: 5 * 60_000,
    enabled,
  });
}

export function useCreateUnit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UnitCreate) => unwrap(api.POST("/api/v1/units", { body })),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["units"] }),
  });
}

export function useUpdateUnit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; body: UnitUpdate }) =>
      unwrap(
        api.PATCH("/api/v1/units/{unit_id}", {
          params: { path: { unit_id: input.id } },
          body: input.body,
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["units"] }),
  });
}
