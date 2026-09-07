import { RichTextView } from '@/components/RichText'
import { EmailEntry } from './EmailEntry'
import { Avatar, Tooltip } from '@/components/ui/primitives'
import { formatDate, timeAgo } from '@/lib/format'
import { useUsers } from '@/list/useLookups'
import type { ActivityEntry } from './types'

/**
 * The record's audit trail.
 *
 * `get_activities` returns entries whose `data` is a string for `creation` and an object
 * for `changed` (`activities.py`), so the renderer branches on `activity_type` rather
 * than trusting one shape. That is Frappe's design, reproduced rather than normalised —
 * normalising it here would put a translation layer between the API and the screen that
 * the next reader would have to reverse.
 */
export function ActivityTimeline({
  activities,
  isPending,
  emptyText = 'Nothing has happened here yet.',
}: {
  activities: ActivityEntry[]
  isPending?: boolean
  emptyText?: string
}) {
  const { getUser } = useUsers()

  if (isPending) {
    return <Empty text="Loading activity…" />
  }
  if (!activities.length) {
    return <Empty text={emptyText} />
  }

  return (
    <ol className="flex flex-col gap-4 p-5">
      {activities.map((entry, index) => {
        // An email is a whole card, not a sentence with an avatar in front of it — it has
        // a subject, recipients, a body and attachments. It gets its own row shape.
        if (entry.activity_type === 'communication') {
          return (
            <li key={`${entry.creation}-${index}`}>
              <EmailEntry entry={entry} />
            </li>
          )
        }

        const user = getUser(entry.owner)
        return (
          <li key={`${entry.creation}-${index}`} className="flex items-start gap-3">
            <Avatar image={user.user_image} label={user.full_name} size="md" />
            <div className="min-w-0 flex-1 text-base text-ink-gray-7">
              <span className="font-medium text-ink-gray-8">{user.full_name}</span>{' '}
              {describe(entry)}
              <Tooltip text={formatDate(entry.creation, true)}>
                <span className="ml-2 text-sm text-ink-gray-4">
                  {timeAgo(entry.creation)}
                </span>
              </Tooltip>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function describe(entry: ActivityEntry): React.ReactNode {
  if (entry.activity_type === 'comment') {
    return (
      <>
        commented
        <div className="mt-1 rounded border border-outline-gray-1 bg-surface-gray-1 p-2">
          {/* `content` is stored verbatim as whatever the client sent (`comment.py:118`),
              and both clients now send HTML. `RichTextView` sanitises every render — the
              author of a comment is another user, and some of them are on the Vue client,
              so an unsanitised render here is stored XSS. */}
          <RichTextView html={entry.content} />
        </div>
      </>
    )
  }

  if (isVersion(entry.activity_type) && entry.data && typeof entry.data === 'object') {
    // Consecutive changes by the same person collapse into one row with the rest hung off
    // `other_versions` (`activities.py:322`), which is what makes a timeline show
    // "Alice changed 4 fields" rather than four rows. The count includes this entry.
    const others = Array.isArray(entry.other_versions) ? entry.other_versions : []

    return (
      <>
        {changeSentence(entry)}
        {others.length ? (
          <ul className="mt-1 border-l-2 border-outline-gray-2 pl-3 text-sm text-ink-gray-6">
            {others.map((other, index) => (
              <li key={`${other.creation}-${index}`}>{changeSentence(other)}</li>
            ))}
          </ul>
        ) : null}
      </>
    )
  }
  // `creation` and anything new the backend grows: `data` is a ready-made sentence.
  return <>{typeof entry.data === 'string' ? entry.data : (entry.activity_type ?? '')}</>
}

/** The three shapes `handle_multiple_versions` groups together. */
function isVersion(activityType: unknown) {
  return activityType === 'changed' || activityType === 'added' || activityType === 'removed'
}

/**
 * One field change as a sentence.
 *
 * `added` carries no `old_value` — the backend drops it when there was nothing there
 * (`activities.py:202`) — so "from empty to X" would be noise. `removed` is the mirror;
 * `handle_multiple_versions` groups it, though nothing in this backend emits one yet.
 */
function changeSentence(entry: ActivityEntry): React.ReactNode {
  const change = (entry.data ?? {}) as {
    field_label?: string
    field?: string
    old_value?: unknown
    value?: unknown
  }
  const field = <span className="font-medium">{change.field_label ?? change.field}</span>

  if (entry.activity_type === 'added') {
    return (
      <>
        set {field} to <Value value={change.value} />
      </>
    )
  }
  if (entry.activity_type === 'removed') {
    return <>cleared {field}</>
  }
  return (
    <>
      changed {field} from <Value value={change.old_value} /> to{' '}
      <Value value={change.value} />
    </>
  )
}

function Value({ value }: { value: unknown }) {
  const text = value === null || value === undefined || value === '' ? 'empty' : String(value)
  return <span className="rounded bg-surface-gray-2 px-1 text-ink-gray-8">{text}</span>
}

function Empty({ text }: { text: string }) {
  return (
    <div className="flex h-full items-center justify-center p-10 text-base text-ink-gray-4">
      {text}
    </div>
  )
}
