import { useQuery } from '@tanstack/react-query'
import { getList } from '@/api/resource'
import { Badge, Tooltip } from '@/components/ui/primitives'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { formatDate, timeAgo } from '@/lib/format'
import { formatDuration } from '@/telephony/callStatus'

/**
 * The SLA row at the top of a deal's or lead's side panel — `SLASection.vue`.
 *
 * The document already carries every field this needs; nothing is fetched for it but the
 * list of communication statuses. It is worth having because the SLA fields are the ones a
 * sales manager actually looks at, and they were invisible: `sla_status` and `response_by`
 * are not on the side-panel layout the server returns, so no amount of metadata would have
 * surfaced them.
 *
 * **The label is not fixed.** Upstream calls the row "First Response" until the record has
 * both a first and a last response that disagree, and "Rolling Response" after that
 * (`SLASection.vue:82-91`). Ported as written — the distinction is what tells you whether
 * the clock you are looking at is the original one.
 */
export function SlaSection({
  doc,
  onUpdateField,
}: {
  doc: Record<string, unknown>
  onUpdateField: (fieldname: string, value: unknown) => void
}) {
  const statuses = useQuery({
    queryKey: ['communication-statuses'],
    queryFn: () =>
      getList<{ name: string }>('CRM Communication Status', {
        fields: ['name'],
        limit_page_length: 0,
      }),
    staleTime: Infinity,
    retry: false,
  })

  // No SLA on this record, so no row. Every deal has the columns; only some have values.
  if (!doc.sla_status && !doc.response_by) return null

  const response = describeResponse(doc)
  const communicationStatus = String(doc.communication_status ?? '')

  return (
    <section className="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="w-28 shrink-0 text-sm text-ink-gray-5">{response.label}</span>
        <Tooltip text={response.tooltip}>
          <span>
            <Badge label={response.text} theme={response.theme} />
          </span>
        </Tooltip>
      </div>

      <div className="flex items-center gap-2">
        <span className="w-28 shrink-0 text-sm text-ink-gray-5">Status</span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              {communicationStatus || 'Set status'}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuRadioGroup
              value={communicationStatus}
              onValueChange={(value) => onUpdateField('communication_status', value)}
            >
              {(statuses.data ?? []).map((status) => (
                <DropdownMenuRadioItem key={status.name} value={status.name}>
                  {status.name}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </section>
  )
}

type Response = {
  label: string
  text: string
  tooltip: string
  theme: 'red' | 'green' | 'orange'
}

/** `SLASection.vue:50-91`, ported branch for branch. */
function describeResponse(doc: Record<string, unknown>): Response {
  const slaStatus = String(doc.sla_status ?? '')
  const respondedOn = doc.last_responded_on || doc.first_responded_on
  const responseTime = Number(doc.last_response_time || doc.first_response_time || 0)

  let text = slaStatus
  let tooltip = slaStatus
  let theme: Response['theme'] =
    slaStatus === 'Failed' ? 'red' : slaStatus === 'Fulfilled' ? 'green' : 'orange'

  if (slaStatus === 'First Response Due' || slaStatus === 'Rolling Response Due') {
    const dueAt = doc.response_by
    text = timeAgo(dueAt)
    if (text === 'just now') text = 'In less than a minute'
    tooltip = formatDate(dueAt, true)

    // Overdue reads red whatever the stored status says, because the status only records
    // that a response is *due* — the deadline itself is the thing that has passed.
    if (dueAt && new Date(String(dueAt)) < new Date()) {
      theme = 'red'
      if (text === 'In less than a minute') text = 'less than a minute ago'
    }
  } else if (slaStatus === 'Fulfilled' || slaStatus === 'Failed') {
    text = `${slaStatus} in ${formatDuration(responseTime)}`
    tooltip = formatDate(respondedOn, true)
  }

  const rolling =
    Boolean(doc.first_responded_on) &&
    Boolean(doc.last_responded_on) &&
    (slaStatus !== 'Fulfilled' || doc.first_responded_on !== doc.last_responded_on)

  return { label: rolling ? 'Rolling Response' : 'First Response', text, tooltip, theme }
}
