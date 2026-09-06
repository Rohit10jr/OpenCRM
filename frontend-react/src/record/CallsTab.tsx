import { PhoneIncoming, PhoneMissed, PhoneOutgoing } from 'lucide-react'
import { Badge } from '@/components/ui/primitives'
import { formatDate } from '@/lib/format'
import { formatDuration } from '@/telephony/callStatus'

/**
 * The Calls tab.
 *
 * `get_activities` already returns every field worth showing — `CALL_FIELDS` in
 * `activities.py:39` is direction, status, both numbers, duration, start time, the
 * recording URL and a note — and the tab was rendering two of them through the generic
 * `RecordList`. A call log that says only "Incoming · Completed" is a row you have to click
 * through to learn anything from, and there is nothing to click through to.
 *
 * **The recording is a plain `<audio controls>`.** Upstream's `AudioPlayer.vue` is 233 lines
 * of custom transport with a playback-speed menu and a waveform; the browser's own player
 * does the part that matters. Worth revisiting only if someone actually wants 1.5× playback.
 */
export function CallsTab({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) {
    return (
      <p className="p-10 text-center text-base text-ink-gray-4">
        No calls logged against this record.
      </p>
    )
  }

  return (
    <ul className="flex flex-col p-5">
      {rows.map((row, index) => {
        const type = String(row.type ?? '')
        const status = String(row.status ?? '')
        const incoming = type.toLowerCase() === 'incoming'
        // Frappe's call statuses; anything not "Completed" and not ringing is a miss.
        const missed = ['No Answer', 'Failed', 'Busy', 'Canceled'].includes(status)
        const Icon = missed ? PhoneMissed : incoming ? PhoneIncoming : PhoneOutgoing
        const seconds = Number(row.duration ?? 0)

        return (
          <li
            key={String(row.name ?? index)}
            className="flex items-start gap-3 border-b border-outline-gray-1 py-3 last:border-0"
          >
            <Icon
              className={missed ? 'mt-1 h-4 w-4 text-red-600' : 'mt-1 h-4 w-4 text-ink-gray-5'}
            />

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-base text-ink-gray-8">
                  {/* `from` and `to` are the raw numbers; which one is the other party
                      depends on the direction. */}
                  {incoming ? String(row.from ?? '') : String(row.to ?? '')}
                </span>
                {status ? (
                  <Badge label={status} theme={missed ? 'red' : 'green'} />
                ) : null}
                {seconds > 0 ? (
                  <span className="text-sm text-ink-gray-5">{formatDuration(seconds)}</span>
                ) : null}
              </div>

              <div className="text-sm text-ink-gray-4">
                {row.start_time ? formatDate(row.start_time, true) : null}
              </div>

              {row.note ? (
                <div className="mt-1 rounded border border-outline-gray-1 bg-surface-gray-1 p-2 text-sm text-ink-gray-7">
                  {String(row.note)}
                </div>
              ) : null}

              {row.recording_url ? (
                <audio
                  controls
                  preload="none"
                  className="mt-2 h-8 w-full max-w-sm"
                  src={String(row.recording_url)}
                />
              ) : null}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
