import { useMutation, useQueryClient } from '@tanstack/react-query'
import { SlidersHorizontal } from 'lucide-react'
import { toast } from 'sonner'
import { call, errorMessage } from '@/api/client'
import type { DocField } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

/**
 * Choose which fields appear as quick filters — `QuickFilterField.vue`'s picker.
 *
 * **This is a workspace-wide setting, not a personal one.** `update_quick_filters` writes a
 * `CRM Global Settings` row keyed on the doctype alone (`doc.py:218`), with no user in the
 * key, so a change here changes the row for everybody. The menu says so, because nothing
 * else on this toolbar behaves that way and the difference is invisible otherwise: views,
 * columns and filters are all per-user.
 *
 * Upstream also flips `in_standard_filter` on each field through a Property Setter. This
 * port does not model Property Setter and does not need to — once the Global Settings row
 * exists, `get_quick_filters` reads it and never consults that flag again
 * (`doc.py:205-210`).
 */
export function QuickFilterSettings({
  doctype,
  selected,
  candidates,
}: {
  doctype: string
  /** The fieldnames currently shown, in order. */
  selected: string[]
  /** Everything filterable, from `get_filterable_fields`. */
  candidates: DocField[]
}) {
  const queryClient = useQueryClient()

  const save = useMutation({
    mutationFn: (fieldnames: string[]) =>
      call('crm.api.doc.update_quick_filters', {
        doctype,
        quick_filters: fieldnames,
        // Accepted for signature fidelity and ignored by the server (`doc.py:216`); sent
        // because the endpoint's signature requires it, not because it does anything.
        old_filters: selected,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['quick-filters', doctype] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not change the quick filters')),
  })

  function toggle(fieldname: string) {
    save.mutate(
      selected.includes(fieldname)
        ? selected.filter((item) => item !== fieldname)
        : [...selected, fieldname],
    )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto"
          title="Choose quick filters"
          loading={save.isPending}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-96 w-64 overflow-y-auto">
        <DropdownMenuLabel>Quick filters</DropdownMenuLabel>
        {candidates.map((field) => (
          <DropdownMenuCheckboxItem
            key={field.fieldname}
            checked={selected.includes(field.fieldname)}
            onCheckedChange={() => toggle(field.fieldname)}
            onSelect={(event) => event.preventDefault()}
          >
            {field.label ?? field.fieldname}
          </DropdownMenuCheckboxItem>
        ))}
        <DropdownMenuSeparator />
        <p className="px-2 py-1.5 text-sm text-ink-gray-4">
          These are shared with everyone in this workspace.
        </p>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
