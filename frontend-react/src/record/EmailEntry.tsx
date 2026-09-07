import { useState } from 'react'
import { ChevronDown, ChevronRight, Paperclip } from 'lucide-react'
import { RichTextView } from '@/components/RichText'
import { Avatar, Badge } from '@/components/ui/primitives'
import { formatDate } from '@/lib/format'
import type { ActivityEntry } from './types'

/**
 * One email in the timeline — `EmailArea.vue` plus `EmailContent.vue`.
 *
 * Emails arrive inside `get_activities` as `activity_type: "communication"` with the whole
 * message in `data` (`activities.py:294`). The timeline had no branch for that shape, so
 * every email in the feed rendered as the literal word "communication" — the most
 * important thing on a CRM timeline, showing as one wrong word.
 *
 * **The body is sanitised, and this is the sharpest case for it in the app.** It is HTML
 * that arrived over SMTP from outside the organisation entirely; the comment box at least
 * only carries what another user of this CRM typed. `RichTextView` is the only way HTML is
 * rendered here and it runs DOMPurify every time.
 *
 * Collapsed by default past the first line, because a thread of ten replies is otherwise a
 * page of quoted text with the new message at the bottom.
 */
export function EmailEntry({ entry }: { entry: ActivityEntry }) {
  const [open, setOpen] = useState(false)
  const data = (entry.data ?? {}) as EmailData
  const attachments = Array.isArray(data.attachments) ? data.attachments : []
  const automated = String(entry.communication_type) === 'Automated Message'

  return (
    <div className="rounded border border-outline-gray-1">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-surface-gray-1"
      >
        {open ? (
          <ChevronDown className="mt-1 h-3.5 w-3.5 shrink-0 text-ink-gray-4" />
        ) : (
          <ChevronRight className="mt-1 h-3.5 w-3.5 shrink-0 text-ink-gray-4" />
        )}
        <Avatar label={data.sender_full_name || data.sender} size="sm" />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-base font-medium text-ink-gray-8">
              {data.sender_full_name || data.sender || 'Unknown sender'}
            </span>
            {automated ? <Badge label="Automated" theme="gray" /> : null}
            {attachments.length ? (
              <span className="flex items-center gap-1 text-sm text-ink-gray-4">
                <Paperclip className="h-3 w-3" />
                {attachments.length}
              </span>
            ) : null}
            <span className="ml-auto shrink-0 text-sm text-ink-gray-4">
              {formatDate(entry.communication_date ?? entry.creation, true)}
            </span>
          </div>
          <div className="truncate text-sm text-ink-gray-6">{data.subject}</div>
        </div>
      </button>

      {open ? (
        <div className="border-t border-outline-gray-1 px-3 py-2">
          <dl className="mb-2 grid grid-cols-[3rem_1fr] gap-x-2 text-sm text-ink-gray-5">
            <Line label="To" value={data.recipients} />
            <Line label="Cc" value={data.cc} />
            <Line label="Bcc" value={data.bcc} />
          </dl>

          <RichTextView html={data.content} />

          {attachments.length ? (
            <ul className="mt-2 flex flex-wrap gap-2">
              {attachments.map((file) => (
                <li key={String(file.name)}>
                  <a
                    href={String(file.file_url ?? '')}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1 rounded border border-outline-gray-1 px-2 py-1 text-sm text-ink-gray-7 hover:bg-surface-gray-1"
                  >
                    <Paperclip className="h-3 w-3" />
                    {String(file.file_name ?? file.name)}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function Line({ label, value }: { label: string; value?: string }) {
  if (!value) return null
  return (
    <>
      <dt>{label}</dt>
      <dd className="min-w-0 break-words text-ink-gray-7">{value}</dd>
    </>
  )
}

type EmailData = {
  subject?: string
  content?: unknown
  sender?: string
  sender_full_name?: string
  recipients?: string
  cc?: string
  bcc?: string
  attachments?: Record<string, unknown>[]
}
