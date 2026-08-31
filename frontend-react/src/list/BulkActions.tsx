import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { call, errorMessage } from '@/api/client'
import { keys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/primitives'

/**
 * What you can do with selected rows.
 *
 * Run 1 and 2 shipped row selection whose only action was "Clear", which is a checkbox that
 * does nothing — the kind of half-feature that reads as broken rather than unfinished.
 *
 * Delete is the one bulk action this backend serves (`crm.api.doc.delete_bulk_docs`). It is
 * worth knowing what that endpoint guarantees, because the UI leans on both: permission is
 * checked **per item and the whole batch refused** if any is denied, and the batch is **one
 * transaction** (`doc.py:536`). So there is no partial outcome to report — it either all
 * happened or none of it did, and the confirmation can say so honestly.
 */
export function BulkActions({
  doctype,
  selected,
  onDone,
}: {
  doctype: string
  selected: string[]
  onDone: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  const queryClient = useQueryClient()

  const remove = useMutation({
    mutationFn: () => call('crm.api.doc.delete_bulk_docs', { doctype, items: selected }),
    onSuccess: () => {
      toast.success(`Deleted ${selected.length} ${selected.length === 1 ? 'row' : 'rows'}`)
      queryClient.invalidateQueries({ queryKey: keys.list.doctype(doctype) })
      setConfirming(false)
      onDone()
    },
    onError: (error) => {
      toast.error(errorMessage(error, 'Could not delete'))
      setConfirming(false)
    },
  })

  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setConfirming(true)}>
        <Trash2 className="h-4 w-4" />
        Delete
      </Button>

      {/*
        A confirmation, because this is the only irreversible thing the list can do. Over a
        threshold the server hands the batch to Celery (`doc.py:546`), so a large delete may
        still be running when the toast says it started — the count below is what was asked
        for, not what has finished.
      */}
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent title={`Delete ${selected.length} ${selected.length === 1 ? 'row' : 'rows'}?`}>
          <p className="text-base text-ink-gray-6">
            This cannot be undone. Linked documents are left alone.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="subtle" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              Delete
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
