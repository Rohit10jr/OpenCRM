import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import { useDocList, useDocMutations } from '@/api/hooks'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/primitives'
import { SettingsField } from './SettingsField'
import { SettingsPage } from './SettingsLayout'

/**
 * A settings screen that is just "a list of rows of one doctype, add and remove".
 *
 * Six of the Vue settings screens are exactly that shape — email accounts, email templates,
 * assignment rules, SLA policies, lead-syncing forms, sales hierarchy — differing only in
 * the doctype, the columns shown and the fields on the create form. `EmailAccountList.vue`,
 * `EmailTemplate/`, `AssignmentRules/`, `Sla/`, `LeadSyncing/` and `Hierarchy/` are around
 * 1,400 lines between them, most of it the same list-and-dialog.
 *
 * **This is the settings equivalent of `ListView`**, and it exists for the same reason: the
 * sixth caller should not be the sixth copy. Anything genuinely per-screen goes in
 * `columns` or `fields`.
 *
 * Editing an existing row is not built — these screens create and delete, and the Vue
 * versions open a per-doctype editor for the middle case. Flagged in the run report.
 */

export type DoctypeListField = {
  fieldname: string
  label: string
  type?: 'text' | 'email' | 'password' | 'number' | 'url' | 'checkbox' | 'textarea'
  hint?: string
  placeholder?: string
}

export function DoctypeListSettings({
  doctype,
  title,
  description,
  columns,
  fields,
  emptyText,
}: {
  doctype: string
  title: string
  description?: string
  /** Fieldnames to show per row; the first is the heading, the rest are the subtitle. */
  columns: string[]
  /** The create form. */
  fields: DoctypeListField[]
  emptyText: string
}) {
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState<Record<string, unknown>>({})

  const rows = useDocList<Record<string, unknown>>(doctype, {
    fields: ['name', ...columns],
    limit_page_length: 100,
    order_by: 'modified desc',
  })
  const { create, remove } = useDocMutations(doctype)

  const [heading, ...rest] = columns

  return (
    <SettingsPage
      title={title}
      description={description}
      actions={
        <Button variant="solid" onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" />
          New
        </Button>
      }
    >
      {rows.isPending ? (
        <p className="text-base text-ink-gray-4">Loading…</p>
      ) : rows.isError ? (
        <p className="text-base text-ink-gray-4">
          Could not read {doctype} from this backend.
        </p>
      ) : (rows.data ?? []).length === 0 ? (
        <p className="text-base text-ink-gray-4">{emptyText}</p>
      ) : (
        <ul className="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
          {(rows.data ?? []).map((row) => (
            <li key={String(row.name)} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-base text-ink-gray-8">
                  {String(row[heading] ?? row.name)}
                </p>
                {rest.length ? (
                  <p className="truncate text-sm text-ink-gray-5">
                    {rest
                      .map((field) => row[field])
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                ) : null}
              </div>
              <Button
                variant="ghost"
                size="icon"
                title={`Delete ${row.name}`}
                loading={remove.isPending}
                onClick={() =>
                  remove.mutate(String(row.name), {
                    onError: (error) =>
                      toast.error(errorMessage(error, 'Could not delete')),
                  })
                }
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent title={`New ${title.replace(/s$/, '')}`}>
          <form
            className="flex flex-col gap-1"
            onSubmit={(event) => {
              event.preventDefault()
              create.mutate(draft, {
                onSuccess: () => {
                  toast.success('Created')
                  setDraft({})
                  setCreating(false)
                },
                onError: (error) =>
                  toast.error(errorMessage(error, 'Could not create')),
              })
            }}
          >
            {fields.map((field) => (
              <SettingsField
                key={field.fieldname}
                label={field.label}
                hint={field.hint}
                type={field.type}
                placeholder={field.placeholder}
                value={draft[field.fieldname]}
                onCommit={(value) =>
                  setDraft((current) => ({ ...current, [field.fieldname]: value }))
                }
              />
            ))}
            <Button
              type="submit"
              variant="solid"
              className="mt-3 self-end"
              loading={create.isPending}
            >
              Create
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </SettingsPage>
  )
}
