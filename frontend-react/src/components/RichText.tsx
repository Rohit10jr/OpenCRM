import { useEffect } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import DOMPurify from 'dompurify'
import { Bold, Italic, List, ListOrdered, Strikethrough } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * The rich text editor, and the safe way to render what it produces.
 *
 * `SPIKE_PLAN.md` fixes TipTap as the stack's rich-text layer, and the Vue app's
 * `TextEditor` is a TipTap wrapper — so this is a port of the choice, not a new one. Until
 * run 5 the React client sent plain text from textareas for comments, emails and notes,
 * while the Vue client stored HTML for all three. That mismatch is divergence 6.
 *
 * **`RichTextView` is the more important half of this file.** Content in these fields is
 * HTML *authored by another user* — anyone on the Vue client — so rendering it with
 * `dangerouslySetInnerHTML` unsanitised is stored XSS with a Vue-shaped delivery mechanism.
 * Every render goes through DOMPurify. There is no unsanitised path in this file on
 * purpose: if you find yourself wanting one, that is the bug.
 */

export function RichTextEditor({
  value,
  placeholder,
  disabled,
  onChange,
  className,
}: {
  value: string
  placeholder?: string
  disabled?: boolean
  onChange: (html: string) => void
  className?: string
}) {
  const editor = useEditor({
    extensions: [StarterKit],
    content: value,
    editable: !disabled,
    onUpdate: ({ editor: instance }) => onChange(instance.getHTML()),
    editorProps: {
      attributes: {
        class:
          'prose prose-sm max-w-none min-h-24 px-2 py-1.5 focus:outline-none text-ink-gray-8',
      },
    },
  })

  // The caller can reset the field — sending a comment clears it — and TipTap holds its own
  // document, so it has to be told. Guarded on inequality or every keystroke would reset
  // the selection to the end.
  useEffect(() => {
    if (editor && value !== editor.getHTML()) {
      editor.commands.setContent(value, { emitUpdate: false })
    }
  }, [editor, value])

  if (!editor) return null

  return (
    <div className={cn('rounded border border-outline-gray-2 bg-surface-white', className)}>
      <div className="flex items-center gap-0.5 border-b border-outline-gray-1 px-1 py-1">
        <ToolbarButton
          label="Bold"
          icon={Bold}
          active={editor.isActive('bold')}
          onClick={() => editor.chain().focus().toggleBold().run()}
        />
        <ToolbarButton
          label="Italic"
          icon={Italic}
          active={editor.isActive('italic')}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        />
        <ToolbarButton
          label="Strikethrough"
          icon={Strikethrough}
          active={editor.isActive('strike')}
          onClick={() => editor.chain().focus().toggleStrike().run()}
        />
        <ToolbarButton
          label="Bullet list"
          icon={List}
          active={editor.isActive('bulletList')}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        />
        <ToolbarButton
          label="Numbered list"
          icon={ListOrdered}
          active={editor.isActive('orderedList')}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        />
      </div>

      {editor.isEmpty && placeholder ? (
        <p className="pointer-events-none absolute px-2 py-1.5 text-base text-ink-gray-4">
          {placeholder}
        </p>
      ) : null}
      <EditorContent editor={editor} />
    </div>
  )
}

function ToolbarButton({
  label,
  icon: Icon,
  active,
  onClick,
}: {
  label: string
  icon: typeof Bold
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'rounded p-1.5 text-ink-gray-6 hover:bg-surface-gray-2',
        active && 'bg-surface-gray-3 text-ink-gray-9',
      )}
    >
      <Icon className="h-3.5 w-3.5" />
    </button>
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
