import { useState } from 'react'
import { toast } from 'sonner'
import {
  BookmarkPlus,
  Copy,
  Globe,
  Lock,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Star,
  Trash2,
} from 'lucide-react'
import { errorMessage } from '@/api/client'
import type { Filters, SavedView, ViewType } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { FormControl } from '@/components/ui/input'
import { Dialog, DialogContent } from '@/components/ui/primitives'
import { useViewMutations } from './useViews'

/**
 * The saved-view picker and everything you can do to a view — `ViewModal.vue` plus the
 * per-row menu that lives in `ViewControls.vue`.
 *
 * The mutations were written in run 4 and nothing reached them: pin, public and
 * set-as-default existed in `useViewMutations` with no button attached. This is the button.
 * It calls them directly rather than taking six more props, because the only thing the
 * parent needs to know is which view is selected.
 *
 * Pinned views sort first, matching upstream — pinning is the only reason to pin.
 */
export function ViewPicker({
  doctype,
  views,
  current,
  viewType,
  filters,
  orderBy,
  onSelect,
  onDeleted,
  canSave,
}: {
  doctype: string
  views: SavedView[]
  current?: string
  viewType: ViewType
  filters: Filters
  orderBy: string
  onSelect: (name?: string) => void
  /** Called after a delete so the caller can drop the view from the URL. */
  onDeleted: (name: string) => void
  canSave: boolean
}) {
  const mutations = useViewMutations(doctype)
  const selected = views.find((view) => String(view.name) === String(current))
  const [naming, setNaming] = useState(false)
  const [renaming, setRenaming] = useState<SavedView>()

  const sorted = [...views].sort(
    (a, b) => Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)),
  )

  function fail(fallback: string) {
    return (error: unknown) => toast.error(errorMessage(error, fallback))
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm">
            {selected?.pinned ? <Pin className="h-3.5 w-3.5" /> : null}
            {selected?.label ?? 'All'}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="max-h-80 w-64 overflow-y-auto">
          <DropdownMenuLabel>Views</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={current ?? ''}
            onValueChange={(value) => onSelect(value || undefined)}
          >
            <DropdownMenuRadioItem value="">All</DropdownMenuRadioItem>
            {sorted.map((view) => (
              <DropdownMenuRadioItem key={view.name} value={String(view.name)}>
                <span className="flex flex-1 items-center gap-1.5 truncate">
                  <span className="truncate">{view.label || view.name}</span>
                  {view.pinned ? <Pin className="h-3 w-3 shrink-0 text-ink-gray-4" /> : null}
                  {view.public ? (
                    <Globe className="h-3 w-3 shrink-0 text-ink-gray-4" />
                  ) : null}
                </span>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      aria-label={`Manage ${view.label || view.name}`}
                      className="rounded p-0.5 text-ink-gray-4 hover:bg-surface-gray-3 hover:text-ink-gray-7"
                      // Without this the radio item selects the view the menu is about.
                      onClick={(event) => {
                        event.preventDefault()
                        event.stopPropagation()
                      }}
                    >
                      <MoreHorizontal className="h-3.5 w-3.5" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-48">
                    <DropdownMenuItem onSelect={() => setRenaming(view)}>
                      <Pencil className="h-4 w-4" />
                      Rename
                    </DropdownMenuItem>

                    <DropdownMenuItem
                      onSelect={() =>
                        mutations.create.mutate(
                          {
                            label: `${view.label || view.name} (copy)`,
                            type: (view.type as ViewType) || 'list',
                            // The copy carries the *stored* filters, not the ones on screen.
                            // Duplicating a view the user is not currently looking at would
                            // otherwise silently take the current screen's filters.
                            filters: parseFilters(view.filters),
                            order_by: view.order_by ?? '',
                          },
                          { onError: fail('Could not duplicate the view') },
                        )
                      }
                    >
                      <Copy className="h-4 w-4" />
                      Duplicate
                    </DropdownMenuItem>

                    <DropdownMenuItem
                      onSelect={() =>
                        mutations.pin.mutate(
                          { name: String(view.name), value: !view.pinned },
                          { onError: fail('Could not pin the view') },
                        )
                      }
                    >
                      {view.pinned ? (
                        <PinOff className="h-4 w-4" />
                      ) : (
                        <Pin className="h-4 w-4" />
                      )}
                      {view.pinned ? 'Unpin' : 'Pin'}
                    </DropdownMenuItem>

                    <DropdownMenuItem
                      onSelect={() =>
                        mutations.setPublic.mutate(
                          { name: String(view.name), value: !view.public },
                          // Only Administrator and Sales Manager may publish
                          // (`view_settings.py:205`), so this is one of the few actions
                          // whose refusal is normal and needs the server's own words.
                          { onError: fail('Could not change who can see this view') },
                        )
                      }
                    >
                      {view.public ? (
                        <Lock className="h-4 w-4" />
                      ) : (
                        <Globe className="h-4 w-4" />
                      )}
                      {view.public ? 'Make private' : 'Make public'}
                    </DropdownMenuItem>

                    <DropdownMenuItem
                      onSelect={() =>
                        mutations.setDefault.mutate(String(view.name), {
                          onSuccess: () => toast.success('This view now opens by default'),
                          onError: fail('Could not set the default'),
                        })
                      }
                    >
                      <Star className="h-4 w-4" />
                      Set as default
                    </DropdownMenuItem>

                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onSelect={() =>
                        mutations.remove.mutate(String(view.name), {
                          onSuccess: () => onDeleted(String(view.name)),
                          onError: fail('Could not delete the view'),
                        })
                      }
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>

          {canSave ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setNaming(true)}>
                <BookmarkPlus className="h-4 w-4" />
                Save current view
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      <NameDialog
        open={naming}
        title="Save this view"
        action="Save view"
        onOpenChange={setNaming}
        onSubmit={(label) =>
          mutations.create.mutate(
            { label, type: viewType, filters, order_by: orderBy },
            {
              onSuccess: (view) => onSelect(String(view.name)),
              onError: fail('Could not save the view'),
            },
          )
        }
      />

      <NameDialog
        open={Boolean(renaming)}
        title="Rename this view"
        action="Rename"
        initial={renaming?.label ?? ''}
        onOpenChange={(open) => !open && setRenaming(undefined)}
        onSubmit={(label) => {
          if (!renaming) return
          mutations.update.mutate(
            { name: String(renaming.name), changes: { label } },
            { onError: fail('Could not rename the view') },
          )
        }}
      />
    </>
  )
}

/** Views store their filters as a JSON string; a malformed one is not worth a crash. */
function parseFilters(raw: string | undefined): Filters {
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function NameDialog({
  open,
  title,
  action,
  initial = '',
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  title: string
  action: string
  initial?: string
  onOpenChange: (open: boolean) => void
  onSubmit: (label: string) => void
}) {
  const [label, setLabel] = useState(initial)

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Reset on open rather than on close, so the field is right the moment it appears
        // — `initial` changes when a different view is picked for renaming.
        if (next) setLabel(initial)
        onOpenChange(next)
      }}
    >
      <DialogContent title={title}>
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!label.trim()) return
            onSubmit(label.trim())
            onOpenChange(false)
          }}
        >
          <FormControl
            label="Name"
            value={label}
            autoFocus
            required
            onChange={(event) => setLabel(event.target.value)}
          />
          <Button type="submit" variant="solid" className="self-end">
            {action}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

