import { useQuery } from '@tanstack/react-query'
import { callGet } from '@/api/client'
import { keys } from '@/api/queryKeys'
import { getList } from '@/api/resource'

/**
 * The reference data a list row needs to render: who a user id belongs to, what colour a
 * status is, which logo an organization has.
 *
 * These are the Pinia stores `users`, `statuses` and `organizations` (~790 lines across
 * ten stores in the Vue app). In React they are query keys, not a state library — a
 * cached fetch plus a lookup function is all any of them was.
 *
 * `staleTime: Infinity`: none of this changes while a list is open, and every row asks
 * for it.
 */

export type CrmUser = {
  name: string
  full_name?: string
  user_image?: string
}

export type CrmStatus = {
  name: string
  color?: string
  position?: number
  type?: string
}

export function useUsers() {
  const query = useQuery({
    queryKey: keys.users,
    queryFn: () => callGet<{ crmUsers?: CrmUser[] }>('crm.api.session.get_users'),
    staleTime: Infinity,
  })

  const byName = new Map((query.data?.crmUsers ?? []).map((u) => [u.name, u]))
  // Falls back to the id itself, which is an email address and is what the Vue app shows
  // before the users resource resolves.
  const getUser = (name?: string | null): CrmUser =>
    (name && byName.get(name)) || { name: name ?? '', full_name: name ?? '' }

  return { getUser, isPending: query.isPending }
}

/**
 * Status rows for one doctype, e.g. `CRM Deal Status`. Colour is the only thing the list
 * needs from them, and it drives the dot beside a status label.
 */
export function useStatuses(statusDoctype: string) {
  const query = useQuery({
    queryKey: keys.statuses(statusDoctype),
    queryFn: () =>
      getList<CrmStatus>(statusDoctype, {
        fields: ['name', 'color', 'position', 'type'],
        order_by: 'position asc',
        limit_page_length: 0,
      }),
    staleTime: Infinity,
  })

  const byName = new Map((query.data ?? []).map((s) => [s.name, s]))
  const getStatus = (name?: string | null) => (name ? byName.get(name) : undefined)

  return { statuses: query.data ?? [], getStatus }
}
