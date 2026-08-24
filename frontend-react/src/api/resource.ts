import { client, encodeParams } from './client'

/**
 * `/api/resource/*` — Frappe's generic CRUD surface (PORT_PLAN.md section 3).
 *
 * These are plain async functions, not hooks. Everything that needs caching wraps them
 * in `useQuery`/`useMutation` in `hooks.ts`; keeping the transport separate means a
 * mutation and a prefetch can share one function.
 *
 * The envelope here is `{ data: ... }`, not `{ message: ... }` — that difference between
 * `/api/resource` and `/api/method` is Frappe's, and it is the reason these two files
 * exist rather than one.
 */

export type DocName = string

export type ListParams = {
  fields?: string[]
  filters?: unknown
  or_filters?: unknown
  order_by?: string
  limit_page_length?: number
  limit_start?: number
}

export async function getDoc<T = Record<string, unknown>>(
  doctype: string,
  name: DocName,
): Promise<T> {
  const response = await client.get<{ data: T }>(
    `/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
  )
  return response.data.data
}

export async function getList<T = Record<string, unknown>>(
  doctype: string,
  params: ListParams = {},
): Promise<T[]> {
  const response = await client.get<{ data: T[] }>(
    `/api/resource/${encodeURIComponent(doctype)}`,
    { params: encodeParams(params as Record<string, unknown>) },
  )
  return response.data.data
}

export async function createDoc<T = Record<string, unknown>>(
  doctype: string,
  doc: Record<string, unknown>,
): Promise<T> {
  const response = await client.post<{ data: T }>(
    `/api/resource/${encodeURIComponent(doctype)}`,
    doc,
  )
  return response.data.data
}

export async function updateDoc<T = Record<string, unknown>>(
  doctype: string,
  name: DocName,
  changes: Record<string, unknown>,
): Promise<T> {
  const response = await client.put<{ data: T }>(
    `/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
    changes,
  )
  return response.data.data
}

export async function deleteDoc(doctype: string, name: DocName): Promise<void> {
  await client.delete(
    `/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
  )
}
