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

/**
 * `crm.api.session.get_users` returns a **tuple** `(users, crm_users)`
 * (`session.py:62`), which arrives as a two-element array.
 *
 * Run 1 read it as `{ crmUsers }`. That is not an error in JavaScript — it is `undefined`
 * — so the map was always empty and `getUser` always fell back to the raw id. The
 * fallback renders an email address, which looks like a plausible answer, so nothing
 * looked broken: every avatar showed one letter of an email and every owner cell showed
 * the address instead of the name. Two endpoints in this API return tuples and both of
 * them have now cost a bug.
 */
type UsersPayload = [users: CrmUser[], crmUsers: CrmUser[]]

export function useUsers() {
  const query = useQuery({
    queryKey: keys.users,
    queryFn: () => callGet<UsersPayload>('crm.api.session.get_users'),
    staleTime: Infinity,
  })

  const [, crmUsers = []] = query.data ?? []
  const byName = new Map(crmUsers.map((user) => [user.name, user]))
  // Falls back to the id itself, which is an email address and is what the Vue app shows
  // before the users resource resolves.
  const getUser = (name?: string | null): CrmUser =>
    (name && byName.get(name)) || { name: name ?? '', full_name: name ?? '' }

  return { getUser, isPending: query.isPending }
}

/**
 * Status rows for one doctype, e.g. `CRM Deal Status`. Colour is the only thing the list
 * needs from them, and it drives the dot beside a status label.
 *
 * `statusDoctype` is optional because not every list has one — a Task's status is a
 * Select field on the model, not rows in a doctype. Passing nothing must not fetch:
 * without the `enabled` guard this requested `/api/resource/` with an empty name and
 * 404'd once per screen.
 */
export function useStatuses(statusDoctype?: string) {
  const query = useQuery({
    queryKey: keys.statuses(statusDoctype ?? ''),
    queryFn: () =>
      getList<CrmStatus>(statusDoctype as string, {
        fields: ['name', 'color', 'position', 'type'],
        order_by: 'position asc',
        limit_page_length: 0,
      }),
    enabled: Boolean(statusDoctype),
    staleTime: Infinity,
  })

  const byName = new Map((query.data ?? []).map((s) => [s.name, s]))
  const getStatus = (name?: string | null) => (name ? byName.get(name) : undefined)

  return { statuses: query.data ?? [], getStatus }
}
