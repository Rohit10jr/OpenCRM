import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Send } from 'lucide-react'
import { toast } from 'sonner'
import { call, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'

/**
 * Add a comment to a record.
 *
 * This is half of the Vue `CommunicationArea.vue` — the half that works. The other half,
 * the email composer, posts to `frappe.core.doctype.communication.email.make`, which this
 * backend does not whitelist (`VUE_DIVERGENCES.md` entry 7). Building a Send button that
 * 404s would be worse than not having one, so this ships the comment path alone.
 *
 * A plain textarea, not TipTap. `add_comment` takes `content` as HTML and stores it
 * verbatim, so a rich editor would work — but the editor is a dependency and a component
 * this conversion has not reached, and a comment box that only does plain text is honest
 * about that in a way an empty toolbar would not be.
 */
export function CommentBox({
  doctype,
  name,
  onAdded,
}: {
  doctype: string
  name: string
  onAdded?: () => void
}) {
  const [content, setContent] = useState('')
  const queryClient = useQueryClient()

  const add = useMutation({
    mutationFn: (text: string) =>
      call('crm.api.comment.add_comment', {
        reference_doctype: doctype,
        reference_name: name,
        content: text,
      }),
    onSuccess: () => {
      setContent('')
      // The comment becomes a timeline entry server-side (`activities.py:259`), so the
      // feed is what has to refetch — not the document.
      queryClient.invalidateQueries({ queryKey: ['activities', name] })
      onAdded?.()
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not add the comment')),
  })

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const text = content.trim()
    if (!text) return
    add.mutate(text)
  }

  return (
    <form
      onSubmit={submit}
      className="flex items-end gap-2 border-t border-outline-gray-1 bg-surface-white p-3"
    >
      <textarea
        name="comment"
        rows={2}
        value={content}
        placeholder="Add a comment…"
        disabled={add.isPending}
        onChange={(event) => setContent(event.target.value)}
        onKeyDown={(event) => {
          // Ctrl/Cmd+Enter sends; plain Enter makes a new line. A comment is often more
          // than one line, so Enter-to-send would truncate more thoughts than it saved.
          if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
            event.preventDefault()
            submit(event)
          }
        }}
        className="min-h-16 flex-1 resize-y rounded border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-base text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none focus:ring-2 focus:ring-ink-gray-4 disabled:opacity-50"
      />
      <Button
        type="submit"
        variant="solid"
        loading={add.isPending}
        disabled={!content.trim()}
        title="Comment (Ctrl+Enter)"
      >
        <Send className="h-4 w-4" />
        Comment
      </Button>
    </form>
  )
}
