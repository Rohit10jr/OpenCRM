import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Send } from 'lucide-react'
import { toast } from 'sonner'
import { call, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'
import { isRichTextEmpty, RichTextEditor } from '@/components/RichText'

/**
 * Add a comment to a record.
 *
 * This is half of the Vue `CommunicationArea.vue` — the half that works. The other half,
 * the email composer, posts to `frappe.core.doctype.communication.email.make`, which this
 * backend does not whitelist (`VUE_DIVERGENCES.md` entry 7). Building a Send button that
 * 404s would be worse than not having one, so this ships the comment path alone.
 *
 * **Rich text since run 5.** `add_comment` takes `content` as HTML and stores it verbatim,
 * which is what the Vue client sends; until now React sent plain text and the two clients
 * disagreed about the field's contents. `RichTextEditor` closes that.
 *
 * Rendering those comments back is the half that matters for safety — see
 * `RichTextView`.
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
    // `<p></p>` is what an untouched TipTap document serialises to, so a plain
    // truthiness check would post an empty comment.
    if (isRichTextEmpty(content)) return
    add.mutate(content)
  }

  return (
    <form
      onSubmit={submit}
      className="flex items-end gap-2 border-t border-outline-gray-1 bg-surface-white p-3"
    >
      <div
        className="min-w-0 flex-1"
        onKeyDown={(event) => {
          // Ctrl/Cmd+Enter sends; plain Enter makes a new line — and inside a rich editor
          // Enter also makes paragraphs, so binding it to send would fight the editor.
          if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
            event.preventDefault()
            submit(event)
          }
        }}
      >
        <RichTextEditor
          value={content}
          placeholder="Add a comment…"
          disabled={add.isPending}
          onChange={setContent}
        />
      </div>
      <Button
        type="submit"
        variant="solid"
        loading={add.isPending}
        disabled={isRichTextEmpty(content)}
        title="Comment (Ctrl+Enter)"
      >
        <Send className="h-4 w-4" />
        Comment
      </Button>
    </form>
  )
}
