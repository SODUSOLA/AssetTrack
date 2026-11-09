import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { User, UserCreate, UserRole, UserUpdate } from "@/api/types";

/**
 * Active engineers and admins, who can be given a complaint. Only the head of engineering may
 * list users; anyone else gets a 403, so callers ask only when `enabled`.
 */
export function useAssignableStaff(enabled: boolean) {
  return useQuery({
    queryKey: ["users", "assignable"],
    enabled,
    staleTime: 5 * 60_000,
    queryFn: async ({ signal }): Promise<User[]> => {
      const roles = ["engineer", "admin"] as const;
      const pages = await Promise.all(
        roles.map((role) =>
          unwrap(
            api.GET("/api/v1/users", {
              params: { query: { role, is_active: true, page_size: 100 } },
              signal,
            }),
          ),
        ),
      );
      return pages
        .flatMap((page) => page.items)
        .sort((a, b) => a.full_name.localeCompare(b.full_name));
    },
  });
}

export const USERS_PAGE_SIZE = 20;

export type UserListParams = { page: number; role?: UserRole; is_active?: boolean };

export function useUsers(params: UserListParams) {
  return useQuery({
    queryKey: ["users", "list", params],
    queryFn: ({ signal }) =>
      unwrap(
        api.GET("/api/v1/users", {
          params: { query: { ...params, page_size: USERS_PAGE_SIZE } },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UserCreate) => unwrap(api.POST("/api/v1/users", { body })),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; body: UserUpdate }) =>
      unwrap(
        api.PATCH("/api/v1/users/{user_id}", {
          params: { path: { user_id: input.id } },
          body: input.body,
        }),
      ),
    // A changed role or unit can change who may be assigned complaints, too.
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}
