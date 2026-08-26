import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { callGet, errorMessage } from '@/api/client'
import { useDocMutations } from '@/api/hooks'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/primitives'
import { FieldInput } from './FieldInput'
import type { PanelField, PanelSection } from './types'

/**
 * Create a record, from the doctype's Quick Entry layout.
 *
 * The same shape as the side panel and driven by the same metadata endpoint —
 * `get_fields_layout(doctype, 'Quick Entry')` returns tabs → sections → columns → expanded
 * field objects (`fields_layout.py:112`), and falls back to a sensible default when no
 * layout is stored. So this knows nothing about deals or leads either, and `FieldInput`
 * does the per-fieldtype work it already does for the panel.
 *
 * **One divergence from Vue, deliberate and worth knowing.** `DealModal.vue:184` posts to
 * `crm.fcrm.doctype.crm_deal.crm_deal.create_deal`, which **this backend does not serve** —
 * it is in `test_phase3_endpoints.py`'s out-of-scope list, and `conversion.py`'s
 * `create_deal` is the lead-conversion helper, a different thing. So this posts to
 * `/api/resource/<doctype>`, the generic surface, which does serve it. What is lost is
 * whatever that controller method did beyond an insert; nothing in the port depends on it
 * today, and it is in the run report.
 */

type LayoutTab = { name: string; sections: PanelSection[] }

export function CreateModal({
  doctype,
  title,
  open,
  onOpenChange,
  onCreated,
}: {
  doctype: string
  title: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: (name: string) => void
}) {
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const { create } = useDocMutations(doctype)

  const layout = useQuery({
    queryKey: ['quick-entry', doctype],
    queryFn: () =>
      callGet<LayoutTab[]>(
        'crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout',
        { doctype, type: 'Quick Entry' },
      ),
    enabled: open,
    staleTime: Infinity,
  })

  // A hidden section in the Quick Entry layout is one the Vue modal reveals through a
  // link-picker it has and this does not; showing its raw fields would be worse than the
  // gap, so they stay hidden here too.
  const sections = (layout.data ?? [])
    .flatMap((tab) => tab.sections ?? [])
    .filter((section) => !(section as { hidden?: boolean }).hidden)

  function submit(event: React.FormEvent) {
    event.preventDefault()
    create.mutate(draft, {
      onSuccess: (created) => {
        const name = String((created as { name?: string })?.name ?? '')
        toast.success(`${title} created`)
        setDraft({})
        onOpenChange(false)
        if (name) onCreated?.(name)
      },
      onError: (error) => toast.error(errorMessage(error, `Could not create the ${title}`)),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={`New ${title}`} className="max-w-2xl">
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <div className="max-h-[60vh] overflow-y-auto pr-1">
            {layout.isPending ? (
              <p className="text-base text-ink-gray-4">Loading…</p>
            ) : (
              sections.map((section) => (
                <fieldset key={section.name} className="mb-4">
                  {section.label ? (
                    <legend className="mb-2 text-sm font-medium text-ink-gray-6">
                      {section.label}
                    </legend>
                  ) : null}
                  <div className="flex flex-col gap-2">
                    {(section.columns ?? []).flatMap((column) =>
                      column.fields.map((field: PanelField) => (
                        <div key={field.fieldname} className="flex items-center gap-2">
                          <label className="w-32 shrink-0 truncate text-sm text-ink-gray-5">
                            {field.label}
                          </label>
                          <div className="min-w-0 flex-1">
                            <FieldInput
                              field={field}
                              value={draft[field.fieldname]}
                              onCommit={(value) =>
                                setDraft((current) => ({
                                  ...current,
                                  [field.fieldname]: value,
                                }))
                              }
                            />
                          </div>
                        </div>
                      )),
                    )}
                  </div>
                </fieldset>
              ))
            )}
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="solid" loading={create.isPending}>
              Create
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
