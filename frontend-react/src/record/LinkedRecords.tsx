import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { MoreHorizontal, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import { useDocMutations } from '@/api/hooks'
import { RichTextView } from '@/components/RichText'
import { Badge } from '@/components/ui/primitives'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { formatDate, timeAgo } from '@/lib/format'
import { CreateModal } from './CreateModal'

/**
 * The Tasks and Notes tabs, with the writing half.
 *
 * Until now these were read-only lists of what `get_activities` happened to return, which
 * is half a feature: a task you cannot tick off is a reminder that you are using the wrong
 * app. Both doctypes are ordinary documents on the generic `/api/resource` surface, and
 * both carry `reference_doctype` / `reference_docname` — which is how a task belongs to a
 * deal. Those two fields are seeded as `defaults` rather than put on the form, because they
 * are context and not a decision.
 *
 * The form itself is `CreateModal`, unchanged in shape: it renders the doctype's Quick
 * Entry layout, so the fields on offer here are whatever the server says a task has. There
 * is deliberately no second, hand-written task form to drift out of step with it.
 *
 * The rows come down inside the record's own `get_activities` payload rather than from a
 * query of their own, so **the key to invalidate is that payload's** — see `refresh` below,
 * and the bug that comment records.
 */
export function LinkedRecords({
  doctype,
  label,
  rows,
  parentDoctype,
  parentName,
  emptyText,
  render,
}: {
  /** The doctype of the rows — `CRM Task` or `FCRM Note`. */
  doctype: string
  /** Singular, for the buttons: "Task", "Note". */
  label: string
  rows: Record<string, unknown>[]
  parentDoctype: string
  parentName: string
  emptyText: string
  render: (row: Record<string, unknown>) => React.ReactNode
}) {
  const queryClient = useQueryClient()
  const { remove } = useDocMutations(doctype)
  const [editing, setEditing] = useState<string>()
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState<Record<string, unknown>>({})

  /**
   * The rows come down inside the record's `get_activities` payload, which lives under
   * `['activities', name]` — *not* under `['doc']`.
   *
   * This invalidated `keys.doc.all` until the browser harness caught it. The two key
   * spaces never intersect, so creating, editing or deleting a task refreshed nothing and
   * the change appeared only after a manual page reload. Every mutation looked like it had
   * silently failed.
   */
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ['activities', parentName] })

  const linkDefaults = {
    reference_doctype: parentDoctype,
    reference_docname: parentName,
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-end border-b border-outline-gray-1 px-5 py-2">
        <Button
          variant="subtle"
          size="sm"
          onClick={() => {
            setDraft(linkDefaults)
            setEditing(undefined)
            setCreating(true)
          }}
        >
          <Plus className="h-4 w-4" />
          New {label.toLowerCase()}
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {rows.length === 0 ? (
          <p className="p-10 text-center text-base text-ink-gray-4">{emptyText}</p>
        ) : (
          <ul className="flex flex-col p-5">
            {rows.map((row, index) => (
              <li
                key={String(row.name ?? index)}
                className="flex items-start gap-2 border-b border-outline-gray-1 py-3 last:border-0"
              >
                <div className="min-w-0 flex-1">{render(row)}</div>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm" aria-label={`Actions for this ${label.toLowerCase()}`}>
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      onSelect={() => {
                        // The row already holds every field the layout will ask for, so the
                        // edit form opens filled in without a second fetch.
                        setDraft({ ...row, ...linkDefaults })
                        setEditing(String(row.name))
                        setCreating(true)
                      }}
                    >
                      Edit
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() =>
                        remove.mutate(String(row.name), {
                          onSuccess: () => {
                            toast.success(`${label} deleted`)
                            void refresh()
                          },
                          onError: (error) =>
                            toast.error(
                              errorMessage(error, `Could not delete the ${label.toLowerCase()}`),
                            ),
                        })
                      }
                    >
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </li>
            ))}
          </ul>
        )}
      </div>

      <CreateModal
        doctype={doctype}
        title={label}
        open={creating}
        onOpenChange={setCreating}
        defaults={draft}
        editName={editing}
        onCreated={() => void refresh()}
      />
    </div>
  )
}

/** A task row: title, description, and the three fields that say what to do about it. */
export function TaskRow({ row }: { row: Record<string, unknown> }) {
  const status = String(row.status ?? '')
  const priority = String(row.priority ?? '')

  return (
    <>
      <div className="flex items-center gap-2">
        <span className="truncate text-base text-ink-gray-8">{String(row.title ?? '')}</span>
        {status ? <Badge label={status} theme={statusTheme(status)} /> : null}
        {priority ? <Badge label={priority} theme={priorityTheme(priority)} /> : null}
      </div>
      {row.description ? (
        <RichTextView html={row.description} className="mt-1 text-sm" />
      ) : null}
      <div className="mt-1 text-sm text-ink-gray-4">
        {row.due_date ? <>Due {formatDate(row.due_date)} · </> : null}
        {row.creation ? timeAgo(row.creation) : null}
      </div>
    </>
  )
}

/** A note row. `content` is HTML from either client, so it goes through the sanitiser. */
export function NoteRow({ row }: { row: Record<string, unknown> }) {
  return (
    <>
      <div className="truncate text-base font-medium text-ink-gray-8">
        {String(row.title ?? 'Untitled')}
      </div>
      <RichTextView html={row.content} className="mt-1 text-sm" />
      <div className="mt-1 text-sm text-ink-gray-4">
        {row.creation ? timeAgo(row.creation) : null}
      </div>
    </>
  )
}

// `CRM Task`'s status and priority are Select fields, so these are the model's own choices
// rather than rows in a `* Status` doctype — nothing to look a colour up from.
function statusTheme(status: string) {
  if (status === 'Done') return 'green' as const
  if (status === 'Cancelled') return 'red' as const
  if (status === 'In Progress') return 'blue' as const
  return 'gray' as const
}

function priorityTheme(priority: string) {
  if (priority === 'High') return 'red' as const
  if (priority === 'Medium') return 'orange' as const
  return 'gray' as const
}
