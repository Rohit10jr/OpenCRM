import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { call, errorMessage } from '@/api/client'
import { keys } from '@/api/queryKeys'
import type { ListColumn, SavedView, ViewType } from '@/api/types'

/**
 * Persist a list's column set.
 *
 * Until now the Columns menu hid columns in component state, which lasted until the page
 * reloaded. Columns live on `CRM View Settings` and `get_data` reads them back, so this is
 * a write, not a preference — the Vue app has always treated it that way.
 *
 * **Two endpoints, because there are two cases.** With a named view selected the change
 * belongs to that view and goes through `crm_view_settings.update`. Without one it belongs
 * to *this user's* default for this doctype and view type, which is what
 * `create_or_update_standard_view` upserts (`view_settings.py:277`) and what `get_data`'s
 * step 3 looks up. Writing a named view in the second case would create a view the user
 * never asked for and would then see in their sidebar.
 *
 * Both go through the endpoints rather than `set_value`, because both merge the default
 * rows and re-sync the column set on the way through.
 */
export function useColumnSettings({
  doctype,
  viewType,
  view,
}: {
  doctype: string
  viewType: ViewType
  /** The named view in play, if any. */
  view?: SavedView
}) {
  const queryClient = useQueryClient()

  const save = useMutation({
    mutationFn: (columns: ListColumn[]) => {
      const payload = {
        name: view?.name,
        doctype,
        type: viewType,
        // The server JSON-encodes what it stores (`view_settings.py:134`), and
        // `parse_json_param` accepts either shape on the way in. Sent as a real array.
        columns,
        // Off, or the server would put the doctype's defaults back over the top of the
        // set that was just chosen (`view_settings.py:126`).
        load_default_columns: false,
      }

      return view
        ? call('crm.fcrm.doctype.crm_view_settings.crm_view_settings.update', {
            view: payload,
          })
        : call(
            'crm.fcrm.doctype.crm_view_settings.crm_view_settings.create_or_update_standard_view',
            { view: payload },
          )
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.list.doctype(doctype) })
      void queryClient.invalidateQueries({ queryKey: ['views', doctype] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not save the columns')),
  })

  /** Put the doctype's own defaults back, by asking the server for them again. */
  const reset = useMutation({
    mutationFn: () => {
      const payload = {
        name: view?.name,
        doctype,
        type: viewType,
        columns: [],
        // The flag that means "ask the doctype", which is exactly what a reset wants.
        load_default_columns: true,
      }
      return view
        ? call('crm.fcrm.doctype.crm_view_settings.crm_view_settings.update', {
            view: payload,
          })
        : call(
            'crm.fcrm.doctype.crm_view_settings.crm_view_settings.create_or_update_standard_view',
            { view: payload },
          )
    },
    onSuccess: () => {
      toast.success('Columns reset')
      void queryClient.invalidateQueries({ queryKey: keys.list.doctype(doctype) })
      void queryClient.invalidateQueries({ queryKey: ['views', doctype] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not reset the columns')),
  })

  return { save, reset }
}
