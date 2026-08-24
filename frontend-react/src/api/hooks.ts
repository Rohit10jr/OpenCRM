import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query'
import { call, callGet } from './client'
import { keys } from './queryKeys'
import {
  createDoc,
  deleteDoc,
  getDoc,
  getList,
  updateDoc,
  type ListParams,
} from './resource'
import type { GetDataParams, GetDataResponse } from './types'

/**
 * The `createResource` → TanStack Query mapping. ~90 call sites in the Vue app ride on
 * this, so the shape is worth stating explicitly:
 *
 * | `createResource`        | here                                            |
 * |-------------------------|-------------------------------------------------|
 * | `auto: true`            | `useQuery` — fetches on mount, that is the default |
 * | `auto: false` + `.submit()` | `useMutation` — an imperative call with arguments |
 * | `params`                | part of the query key, so changing them refetches |
 * | `cache: [...]`          | `queryKey` (see `queryKeys.ts`)                 |
 * | `.reload()`             | `refetch()`, or `invalidateQueries` from elsewhere |
 * | `.loading` / `.data` / `.error` | `isPending` / `data` / `error`          |
 * | `onSuccess` / `onError` | `onSuccess`/`onError` on a mutation; for a query, handle in render |
 *
 * The one real behavioural difference is worth naming rather than hiding: `createResource`
 * refetched whenever `params` changed *and* kept the previous `data` visible while it did.
 * TanStack does the first for free — a new key is a new query — but by default shows
 * `undefined` during the transition. `placeholderData: keepPreviousData` restores the Vue
 * behaviour and is set on `useGetData` below, because the list screens flicker without it.
 */

/**
 * `crm.api.doc.get_data` — the list/kanban engine.
 *
 * GET rather than POST: it is a read, the backend whitelists both verbs, and a GET keeps
 * the request visible in devtools, which matters for a screen whose whole job is
 * assembling a complicated query.
 */
export function useGetData(
  params: GetDataParams,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: keys.list.view(params.doctype, params),
    queryFn: () => callGet<GetDataResponse>('crm.api.doc.get_data', params),
    enabled: options?.enabled ?? true,
    // Matches `createResource`: params change, data refetches, old rows stay on screen
    // until the new ones land. Without this every filter keystroke blanks the table.
    placeholderData: (previous) => previous,
  })
}

/** A single document by name. The React answer to `createDocumentResource`. */
export function useDoc<T = Record<string, unknown>>(
  doctype: string,
  name: string | undefined,
  options?: Partial<UseQueryOptions<T>>,
) {
  return useQuery({
    queryKey: keys.doc.one(doctype, name ?? ''),
    queryFn: () => getDoc<T>(doctype, name as string),
    enabled: Boolean(name),
    ...options,
  })
}

/** A filtered list straight off `/api/resource`. The answer to `createListResource`. */
export function useDocList<T = Record<string, unknown>>(
  doctype: string,
  params: ListParams = {},
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: keys.doc.list(doctype, params),
    queryFn: () => getList<T>(doctype, params),
    enabled: options?.enabled ?? true,
  })
}

/** Any whitelisted method, read-only. The answer to `call` used inside a `createResource`. */
export function useMethod<T = unknown>(
  method: string,
  params: Record<string, unknown> = {},
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: [method, params],
    queryFn: () => callGet<T>(method, params),
    enabled: options?.enabled ?? true,
  })
}

/**
 * Any whitelisted method, as a mutation. The answer to `createResource({ auto: false })`
 * followed by `.submit(args)`.
 *
 * Invalidation is the caller's job — this cannot know what a given method wrote.
 */
export function useCallMethod<TResult = unknown, TArgs extends Record<string, unknown> = Record<string, unknown>>(
  method: string,
) {
  return useMutation({
    mutationFn: (args: TArgs) => call<TResult>(method, args),
  })
}

/**
 * Create / update / delete for one doctype, with the invalidation already wired.
 *
 * Every write invalidates both this doctype's lists and its documents, because a write
 * can move a row between list views (a status change reorders the kanban) and there is
 * no cheap way to know from here which views were affected. Refetching more than
 * strictly necessary is the right default; being subtly stale is not.
 */
export function useDocMutations(doctype: string) {
  const queryClient = useQueryClient()

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: keys.list.doctype(doctype) })
    queryClient.invalidateQueries({ queryKey: keys.doc.all })
  }

  const create = useMutation({
    mutationFn: (doc: Record<string, unknown>) => createDoc(doctype, doc),
    onSuccess: invalidate,
  })

  const update = useMutation({
    mutationFn: ({ name, changes }: { name: string; changes: Record<string, unknown> }) =>
      updateDoc(doctype, name, changes),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (name: string) => deleteDoc(doctype, name),
    onSuccess: invalidate,
  })

  return { create, update, remove, invalidate }
}
