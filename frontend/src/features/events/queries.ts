import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";

export function useRecentEvents(pageSize = 8) {
  return useQuery({
    queryKey: ["events", "recent", pageSize],
    queryFn: ({ signal }) =>
      unwrap(
        api.GET("/api/v1/events", { params: { query: { page: 1, page_size: pageSize } }, signal }),
      ),
  });
}
