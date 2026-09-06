import { useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
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
 * Editing goes through the same form as creating, which is the whole reason it was cheap to
 * add to all six at once: the fields a screen declares are the fields it edits. The Vue app
 * has a hand-written editor per doctype — `EditEmailTemplate.vue` alone is 246 lines — and
 * those editors do carry per-doctype affordances this does not, chiefly the rich-text body
 * on an email template. Recorded in `VUE_DIVERGENCES.md`.
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
  /** The form, used for both create and edit. */
  fields: DoctypeListField[]
  emptyText: string
}) {
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<string>()
  const [draft, setDraft] = useState<Record<string, unknown>>({})

  // The editable fields are fetched too, not just the ones shown: the edit form asks for
  // whatever the screen declared, and a row that arrived without those would open blank
  // and then blank them on save.
  const fieldnames = Array.from(
    new Set(['name', ...columns, ...fields.map((field) => field.fieldname)]),
  )

  const rows = useDocList<Record<string, unknown>>(doctype, {
    fields: fieldnames,
    limit_page_length: 100,
    order_by: 'modified desc',
  })
  const { create, update, remove } = useDocMutations(doctype)

  const [heading, ...rest] = columns

  return (
    <SettingsPage
      title={title}
      description={description}
      actions={
        <Button
          variant="solid"
          onClick={() => {
            setDraft({})
            setEditing(undefined)
            setCreating(true)
          }}
        >
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
                size="sm"
                onClick={() => {
                  setDraft({ ...row })
                  setEditing(String(row.name))
                  setCreating(true)
                }}
              >
                <Pencil className="h-4 w-4" />
                Edit
              </Button>
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
        <DialogContent
          title={`${editing ? 'Edit' : 'New'} ${title.replace(/s$/, '').toLowerCase()}`}
        >
          <form
            className="flex flex-col gap-1"
            onSubmit={(event) => {
              event.preventDefault()
              const done = (message: string) => () => {
                toast.success(message)
                setDraft({})
                setEditing(undefined)
                setCreating(false)
              }

              if (editing) {
                update.mutate(
                  { name: editing, changes: draft },
                  {
                    onSuccess: done('Saved'),
                    onError: (error) => toast.error(errorMessage(error, 'Could not save')),
                  },
                )
                return
              }

              create.mutate(draft, {
                onSuccess: done('Created'),
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
                // A document's name is set at insert and renaming is a different operation
                // entirely, so the field that names the row is read-only once it exists.
                disabled={Boolean(editing) && field.fieldname === 'name'}
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
              loading={create.isPending || update.isPending}
            >
              {editing ? 'Save' : 'Create'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </SettingsPage>
  )
}
