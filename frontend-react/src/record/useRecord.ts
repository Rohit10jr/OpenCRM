import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { call, callGet } from '@/api/client'
import { useDoc } from '@/api/hooks'
import { keys } from '@/api/queryKeys'
import type { ActivitiesPayload, PanelSection } from './types'

/**
 * Everything one record screen reads and writes.
 *
 * The Vue equivalent is `data/document.js`'s `useDocument` — a `createDocumentResource`
 * plus caches for assignees, permissions and form scripts, ~300 lines with a
 * module-level `documentsCache` keyed by doctype and name. None of that is needed here:
 * TanStack Query *is* the cache, and its key is the doctype and name.
 *
 * **Doctype-agnostic on purpose.** Contact and Organization record screens are the next
 * two callers, and the only thing that differs between them is the doctype string.
 */
export function useRecord(doctype: string, name: string) {
  const queryClient = useQueryClient()

  const doc = useDoc(doctype, name)

  /**
   * The side panel's layout. Cached hard: it is site-wide configuration, identical for
   * every record of a doctype, and re-fetching it per record would be one request per
   * navigation for data that changes when an admin edits a settings screen.
   */
  const sections = useQuery({
    queryKey: ['sidepanel', doctype],
    queryFn: () =>
      callGet<PanelSection[]>(
        'crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections',
        { doctype },
      ),
    staleTime: Infinity,
  })

  const assignees = useQuery({
    queryKey: ['assignees', doctype, name],
    queryFn: () => callGet<string[]>('crm.api.doc.get_assigned_users', { doctype, name }),
    enabled: Boolean(name),
  })

  const activities = useQuery({
    queryKey: ['activities', name],
    queryFn: () => callGet<ActivitiesPayload>('crm.api.activities.get_activities', { name }),
    enabled: Boolean(name),
  })

  /**
   * Save one field.
   *
   * `frappe.client.set_value` rather than a `PUT` of the whole document, because that is
   * what the Vue side panel sends and because a whole-document write would clobber a
   * field someone else changed while this screen was open.
   */
  const updateField = useMutation({
    mutationFn: ({ fieldname, value }: { fieldname: string; value: unknown }) =>
      call('frappe.client.set_value', { doctype, name, fieldname, value }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.doc.one(doctype, name) })
      // A status or owner change reorders the list this record was opened from.
      queryClient.invalidateQueries({ queryKey: keys.list.doctype(doctype) })
      queryClient.invalidateQueries({ queryKey: ['activities', name] })
      // Assignment is a server-side consequence of some field writes, not only of an
      // explicit assign — an owner change can rewrite `_assign` — so the header's avatars
      // have to be refetched too.
      queryClient.invalidateQueries({ queryKey: ['assignees', doctype, name] })
    },
  })

  const [activityEntries = [], calls = [], notes = [], tasks = [], attachments = []] =
    activities.data ?? []

  return {
    doc: doc.data,
    isPending: doc.isPending,
    error: doc.error,
    sections: sections.data ?? [],
    assignees: assignees.data ?? [],
    activities: activityEntries,
    calls,
    notes,
    tasks,
    attachments,
    activitiesPending: activities.isPending,
    updateField,
  }
}
