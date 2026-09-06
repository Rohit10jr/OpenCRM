import { lazy, Suspense } from 'react'
import DOMPurify from 'dompurify'
import { cn } from '@/lib/utils'

/**
 * The rich text editor, and the safe way to render what it produces.
 *
 * `SPIKE_PLAN.md` fixes TipTap as the stack's rich-text layer, and the Vue app's
 * `TextEditor` is a TipTap wrapper — so this is a port of the choice, not a new one. Until
 * run 5 the React client sent plain text from textareas for comments and emails while the
 * Vue client stored HTML for both.
 *
 * **The editor is loaded on demand and the viewer is not**, which is the whole reason this
 * file and `RichTextEditorImpl` are separate. TipTap and ProseMirror are about half the
 * bundle; every record screen imports the comment box, so importing the editor directly put
 * all of it in the entry chunk and made it the price of opening a deal. Rendering, by
 * contrast, is needed the moment a timeline has one comment in it — and costs only
 * DOMPurify.
 *
 * **`RichTextView` is the more important half.** Content in these fields is HTML *authored
 * by another user*, anyone on the Vue client included, so rendering it with
 * `dangerouslySetInnerHTML` unsanitised is stored XSS with a Vue-shaped delivery mechanism.
 * Every render goes through DOMPurify. There is no unsanitised path in this file on
 * purpose: if you find yourself wanting one, that is the bug.
 */

const RichTextEditorImpl = lazy(() => import('./RichTextEditorImpl'))

export function RichTextEditor(props: {
  value: string
  placeholder?: string
  disabled?: boolean
  onChange: (html: string) => void
  className?: string
}) {
  return (
    <Suspense
      fallback={
        // Same height as the editor, so the form does not jump when the chunk lands.
        <div className="min-h-32 rounded border border-outline-gray-2 bg-surface-gray-1" />
      }
    >
      <RichTextEditorImpl {...props} />
    </Suspense>
  )
}

/**
 * Render stored HTML.
 *
 * **Always sanitised.** See the file comment — the content is written by other users, and
 * some of them are on a different client.
 */
export function RichTextView({ html, className }: { html: unknown; className?: string }) {
  const source = typeof html === 'string' ? html : ''
  if (!source) return null

  return (
    <div
      className={cn('prose prose-sm max-w-none text-ink-gray-8', className)}
      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(source) }}
    />
  )
}

/** True when the editor holds nothing but empty markup, which is what TipTap returns. */
export function isRichTextEmpty(html: string) {
  return !html || html.replace(/<[^>]*>/g, '').trim() === ''
}
