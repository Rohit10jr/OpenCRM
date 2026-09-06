import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { call, errorMessage } from '@/api/client'
import { getDoc } from '@/api/resource'

/**
 * Read and write a Frappe "Single" doctype — the ones with exactly one row, which is how
 * every settings screen stores itself (`FCRM Settings`, `CRM Telephony Settings`, …).
 *
 * A Single's document name *is* its doctype name, which is why the fetch looks like it is
 * asking for a document called "FCRM Settings" — it is.
 *
 * Writes go field-at-a-time through `set_value`, the same call the record side panel makes,
 * so two people on the settings screen do not clobber each other's unrelated fields.
 */
export function useSettingsDoc<T extends Record<string, unknown>>(doctype: string) {
  const queryClient = useQueryClient()
  const queryKey = ['single', doctype]

  const query = useQuery({
    queryKey,
    queryFn: () => getDoc<T>(doctype, doctype),
    // Settings change rarely and every field on the screen reads this one document.
    staleTime: 60_000,
    retry: false,
  })

  const save = useMutation({
    mutationFn: ({ fieldname, value }: { fieldname: string; value: unknown }) =>
      call('frappe.client.set_value', { doctype, name: doctype, fieldname, value }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
    onError: (error) => toast.error(errorMessage(error, 'Could not save')),
  })

  return {
    doc: query.data,
    isPending: query.isPending,
    /** A Single that has never been saved 404s; that is "not configured", not an error. */
    missing: query.isError,
    save,
    setField: (fieldname: string, value: unknown) => save.mutate({ fieldname, value }),
  }
}
