import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { LayoutGrid } from 'lucide-react'
import { toast } from 'sonner'
import { call, errorMessage } from '@/api/client'
import type { DocField, SavedView } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Checkbox, Dialog, DialogContent } from '@/components/ui/primitives'
import { useGroupByFields } from './useFieldOptions'

/**
 * What the kanban board groups on, and what a card shows — `KanbanSettings.vue`.
 *
 * Both live on the *view*, as `column_field` and `kanban_fields` on `CRM View Settings`, so
 * this can only save when a saved view is selected. On the unsaved "All" view there is
 * nothing to write to, and the dialog says so rather than pretending: upstream quietly
 * creates a default view behind your back at that point, which is a surprise the first time
 * you notice a view you did not make.
 *
 * The write goes through `crm_view_settings.update` rather than `set_value` on the row,
 * because that endpoint merges default rows and re-syncs the column set (`view_settings.py:170`).
 */
export function KanbanSettings({
  doctype,
  view,
  fields,
  columnField,
  cardFields,
}: {
  doctype: string
  /** The saved view being edited, or undefined on the unsaved default. */
  view?: SavedView
  /** Field metadata from the list payload — the candidates for a card. */
  fields: DocField[]
  columnField?: string
  cardFields: string[]
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [column, setColumn] = useState(columnField ?? '')
  const [selected, setSelected] = useState<string[]>(cardFields)

  const groupable = useGroupByFields(doctype)

  const save = useMutation({
    mutationFn: () =>
      call('crm.fcrm.doctype.crm_view_settings.crm_view_settings.update', {
        view: {
          name: view?.name,
          doctype,
          column_field: column,
          kanban_fields: JSON.stringify(selected),
        },
      }),
    onSuccess: () => {
      toast.success('Board updated')
      void queryClient.invalidateQueries({ queryKey: ['views', doctype] })
      void queryClient.invalidateQueries({ queryKey: ['list'] })
      setOpen(false)
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not update the board')),
  })

  function toggle(fieldname: string) {
    setSelected((current) =>
      current.includes(fieldname)
        ? current.filter((item) => item !== fieldname)
        : [...current, fieldname],
    )
  }

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          // Re-read from the payload each time: another client may have changed the board.
          setColumn(columnField ?? '')
          setSelected(cardFields)
          setOpen(true)
        }}
      >
        <LayoutGrid className="h-4 w-4" />
        Board
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent title="Board settings">
          {!view ? (
            <p className="text-base text-ink-gray-5">
              These settings belong to a view. Save the current one first — “Save current
              view” in the view menu — and then come back.
            </p>
          ) : (
            <div className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-sm text-ink-gray-5">Columns come from</span>
                <select
                  className="h-8 rounded border border-outline-gray-2 bg-surface-white px-2 text-base"
                  value={column}
                  onChange={(event) => setColumn(event.target.value)}
                >
                  {groupable.map((field) => (
                    <option key={field.fieldname} value={field.fieldname}>
                      {field.label}
                    </option>
                  ))}
                </select>
              </label>

              <div className="flex flex-col gap-1.5">
                <span className="text-sm text-ink-gray-5">Show on each card</span>
                <ul className="max-h-56 overflow-auto rounded border border-outline-gray-1">
                  {fields.map((field) => (
                    <li key={field.fieldname}>
                      <label className="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-surface-gray-1">
                        <Checkbox
                          checked={selected.includes(field.fieldname)}
                          onCheckedChange={() => toggle(field.fieldname)}
                        />
                        <span className="text-base text-ink-gray-8">{field.label}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>

              <Button
                variant="solid"
                className="self-end"
                loading={save.isPending}
                onClick={() => save.mutate()}
              >
                Save
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
