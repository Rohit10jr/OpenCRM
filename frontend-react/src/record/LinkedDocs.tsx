import { useQuery } from '@tanstack/react-query'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Heart, Link2, Unlink } from 'lucide-react'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { keys } from '@/api/queryKeys'
import { Button } from '@/components/ui/button'
import { parseAssignees } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * What else points at this record.
 *
 * `crm.api.doc.get_linked_docs_of_document` derives the links from the registry — every FK
 * pointing at this doctype, plus the dynamic `reference_doctype`/`reference_name`
 * convention (`doc.py:350`). Served since phase 3 and unused by React until now.
 *
 * The results are permission-filtered server-side, which upstream's version is not: it feeds
 * a "deleting this will also affect these" UI, and listing the titles of documents the
 * caller cannot open would be a leak with no upside. Worth knowing, because it means an
 * empty list here does not prove there are no links.
 */
export function LinkedDocs({ doctype, name }: { doctype: string; name: string }) {
  const queryClient = useQueryClient()

  const linked = useQuery({
    queryKey: ['linked-docs', doctype, name],
    queryFn: () =>
      callGet<Record<string, unknown>[]>('crm.api.doc.get_linked_docs_of_document', {
        doctype,
        docname: name,
      }),
    retry: false,
  })

  const unlink = useMutation({
    mutationFn: (row: Record<string, unknown>) =>
      call('crm.api.doc.remove_linked_doc_reference', {
        doctype: row.reference_doctype ?? row.doctype,
        docname: row.reference_name ?? row.name,
        // The server clears the reference pair rather than deleting the document.
        remove_contact: false,
      }),
    onSuccess: () => {
      toast.success('Link removed')
      queryClient.invalidateQueries({ queryKey: ['linked-docs', doctype, name] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not remove the link')),
  })

  const rows = linked.data ?? []
  if (linked.isError) return null

  return (
    <section className="border-b border-outline-gray-1 px-4 py-3">
      <h3 className="mb-2 flex items-center gap-1.5 text-sm font-medium text-ink-gray-6">
        <Link2 className="h-3.5 w-3.5" />
        Linked documents
      </h3>

      {linked.isPending ? (
        <p className="text-sm text-ink-gray-4">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-ink-gray-4">Nothing links here.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {rows.map((row, index) => (
            <li key={String(row.name ?? index)} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-base text-ink-gray-7">
                {String(row.title ?? row.name ?? '')}
                <span className="ml-1.5 text-sm text-ink-gray-4">
                  {String(row.reference_doctype ?? row.doctype ?? '')}
                </span>
              </span>
              <Button
                variant="ghost"
                size="icon"
                title="Remove this link"
                onClick={() => unlink.mutate(row)}
              >
                <Unlink className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/**
 * Like a record.
 *
 * `_liked_by` is a denormalised cache written with a bare `update()` so a like does **not**
 * bump `modified` (`client.py:290`) — otherwise liking something would reorder every list
 * sorted by last-modified, which is the default sort. So this invalidates the document but
 * deliberately does not invalidate the lists: nothing about their order changed.
 */
export function LikeButton({
  doctype,
  name,
  likedBy,
  currentUser,
}: {
  doctype: string
  name: string
  likedBy: unknown
  currentUser: string | null
}) {
  const queryClient = useQueryClient()
  const likers = parseAssignees(likedBy)
  const liked = Boolean(currentUser && likers.includes(currentUser))

  const toggle = useMutation({
    mutationFn: () =>
      call('frappe.desk.like.toggle_like', { doctype, name, add: liked ? 'No' : 'Yes' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.doc.one(doctype, name) }),
    onError: (error) => toast.error(errorMessage(error, 'Could not update')),
  })

  return (
    <Button
      variant="ghost"
      size="icon"
      title={liked ? 'Unlike' : 'Like'}
      onClick={() => toggle.mutate()}
    >
      <Heart className={cn('h-4 w-4', liked && 'fill-red-500 text-red-500')} />
    </Button>
  )
}
