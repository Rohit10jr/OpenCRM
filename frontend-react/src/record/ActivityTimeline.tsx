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
}: {
  activities: ActivityEntry[]
  isPending?: boolean
}) {
  const { getUser } = useUsers()

  if (isPending) {
    return <Empty text="Loading activity…" />
  }
  if (!activities.length) {
    return <Empty text="Nothing has happened here yet." />
  }

  return (
    <ol className="flex flex-col gap-4 p-5">
      {activities.map((entry, index) => {
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
  if (entry.activity_type === 'changed' && entry.data && typeof entry.data === 'object') {
    const change = entry.data as {
      field_label?: string
      field?: string
      old_value?: unknown
      value?: unknown
    }
    return (
      <>
        changed <span className="font-medium">{change.field_label ?? change.field}</span>{' '}
        from <Value value={change.old_value} /> to <Value value={change.value} />
      </>
    )
  }
  // `creation` and anything new the backend grows: `data` is a ready-made sentence.
  return <>{typeof entry.data === 'string' ? entry.data : (entry.activity_type ?? '')}</>
}

function Value({ value }: { value: unknown }) {
  const text = value === null || value === undefined || value === '' ? 'empty' : String(value)
  return <span className="rounded bg-surface-gray-2 px-1 text-ink-gray-8">{text}</span>
}

/**
 * The Calls / Tasks / Notes / Attachments tabs.
 *
 * `get_activities` returns all four alongside the timeline, so they are already fetched;
 * these render what came back rather than asking again.
 */
export function RecordList({
  rows,
  titleField,
  subtitleField,
  emptyText,
}: {
  rows: Record<string, unknown>[]
  titleField: string
  subtitleField?: string
  emptyText: string
}) {
  if (!rows.length) return <Empty text={emptyText} />

  return (
    <ul className="flex flex-col p-5">
      {rows.map((row, index) => (
        <li
          key={String(row.name ?? index)}
          className="border-b border-outline-gray-1 py-2.5 last:border-0"
        >
          <div className="truncate text-base text-ink-gray-8">
            {String(row[titleField] ?? row.name ?? '')}
          </div>
          {subtitleField && row[subtitleField] ? (
            <div className="truncate text-sm text-ink-gray-5">
              {String(row[subtitleField])}
            </div>
          ) : null}
          {row.creation ? (
            <div className="text-sm text-ink-gray-4">{timeAgo(row.creation)}</div>
          ) : null}
        </li>
      ))}
    </ul>
  )
}

function Empty({ text }: { text: string }) {
  return (
    <div className="flex h-full items-center justify-center p-10 text-base text-ink-gray-4">
      {text}
    </div>
  )
}
