import { useState } from 'react'
import { useParams, useSearch } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import type { DocRow } from '@/api/types'
import { getDoc } from '@/api/resource'
import { Badge, Dialog, DialogContent } from '@/components/ui/primitives'
import { formatDate } from '@/lib/format'
import { ListView } from '@/list/ListView'
import { formatDuration } from '@/telephony/callStatus'

/**
 * Call logs.
 *
 * **No Create button, deliberately.** A call log is written by the telephony integration
 * when a call happens (`crm.integrations.*`), not typed in by hand — the Vue page has no
 * create action either. Adding one here would offer to fabricate call history.
 *
 * Clicking a row opens the detail rather than navigating: a call log has no record screen
 * in either app, and one row of a list is not a page.
 */
export function CallLogsPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })
  const [selected, setSelected] = useState<string>()

  return (
    <>
      <ListView
        doctype="CRM Call Log"
        title="Call Logs"
        basePath="/call-logs/view"
        viewType={viewType}
        savedViewName={view}
        onRowClick={(row: DocRow) => setSelected(String(row.name))}
      />
      <CallLogDetail
        name={selected}
        onOpenChange={(open) => !open && setSelected(undefined)}
      />
    </>
  )
}

/**
 * One call — `CallLogDetailModal.vue`, the reading half.
 *
 * The list payload does not carry every field, so this reads the document. Upstream's modal
 * also *writes*: it attaches a note or a task to the call. That path exists here, in the
 * live call panel (`telephony/CallPanel.tsx`), where it is the natural moment to use it;
 * doing it again from a log row is not built, and is in the run report.
 */
function CallLogDetail({
  name,
  onOpenChange,
}: {
  name?: string
  onOpenChange: (open: boolean) => void
}) {
  const call = useQuery({
    queryKey: ['call-log', name],
    queryFn: () => getDoc<Record<string, unknown>>('CRM Call Log', name as string),
    enabled: Boolean(name),
    retry: false,
  })

  const doc = call.data
  const status = String(doc?.status ?? '')
  const missed = ['No Answer', 'Failed', 'Busy', 'Canceled'].includes(status)
  const seconds = Number(doc?.duration ?? 0)

  return (
    <Dialog open={Boolean(name)} onOpenChange={onOpenChange}>
      <DialogContent title="Call">
        {call.isPending ? (
          <p className="text-base text-ink-gray-4">Loading…</p>
        ) : !doc ? (
          <p className="text-base text-ink-gray-4">Could not read this call.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-2 text-base">
              <Row label="Status">
                <Badge label={status || '—'} theme={missed ? 'red' : 'green'} />
              </Row>
              <Row label="Direction">{String(doc.type ?? '—')}</Row>
              <Row label="From">{String(doc.from ?? '—')}</Row>
              <Row label="To">{String(doc.to ?? '—')}</Row>
              <Row label="Duration">{seconds ? formatDuration(seconds) : '—'}</Row>
              <Row label="Started">
                {doc.start_time ? formatDate(doc.start_time, true) : '—'}
              </Row>
              <Row label="Ended">
                {doc.end_time ? formatDate(doc.end_time, true) : '—'}
              </Row>
              {doc.telephony_medium ? (
                <Row label="Provider">{String(doc.telephony_medium)}</Row>
              ) : null}
            </dl>

            {doc.recording_url ? (
              <audio
                controls
                preload="none"
                className="h-8 w-full"
                src={String(doc.recording_url)}
              />
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-sm text-ink-gray-5">{label}</dt>
      <dd className="min-w-0 truncate text-ink-gray-8">{children}</dd>
    </>
  )
}
