import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useDocList } from '@/api/hooks'
import { Avatar } from '@/components/ui/primitives'
import { formatCurrency, timeAgo } from '@/lib/format'
import { useStatuses } from '@/list/useLookups'
import { cn } from '@/lib/utils'

/**
 * The Deals and Contacts tabs on an organization — `Organization.vue:373-427`.
 *
 * An organization has no activity feed, so `RecordScreen` was showing it a side panel and
 * the sentence "this doctype has no activity feed". True, and useless: what an organization
 * *is*, in this CRM, is the deals and people attached to it.
 *
 * Both are ordinary filtered lists on the generic surface, with the same filters upstream
 * uses — `CRM Deal.organization` and, less obviously, `Contact.company_name`, which holds
 * the organization's *name* rather than a link (`Organization.vue:421`).
 *
 * Not `ListView`: that engine is `get_data` with saved views, filters and a toolbar, none
 * of which belongs in a panel on someone else's record.
 */
export function RelatedLists({ organizationId }: { organizationId: string }) {
  const [tab, setTab] = useState<'deals' | 'contacts'>('deals')

  const deals = useDocList<Record<string, unknown>>('CRM Deal', {
    fields: ['name', 'organization', 'currency', 'deal_value', 'status', 'modified'],
    filters: { organization: organizationId },
    order_by: 'modified desc',
    limit_page_length: 20,
  })

  const contacts = useDocList<Record<string, unknown>>('Contact', {
    fields: ['name', 'full_name', 'image', 'email_id', 'mobile_no', 'modified'],
    filters: { company_name: organizationId },
    order_by: 'modified desc',
    limit_page_length: 20,
  })

  const dealRows = deals.data ?? []
  const contactRows = contacts.data ?? []

  return (
    <div className="flex h-full flex-col">
      <div role="tablist" className="flex shrink-0 gap-5 border-b border-outline-gray-1 px-5">
        <Tab
          id="deals"
          label={`Deals (${dealRows.length})`}
          active={tab === 'deals'}
          onSelect={setTab}
        />
        <Tab
          id="contacts"
          label={`Contacts (${contactRows.length})`}
          active={tab === 'contacts'}
          onSelect={setTab}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-5">
        {tab === 'deals' ? (
          <DealList rows={dealRows} isPending={deals.isPending} />
        ) : (
          <ContactList rows={contactRows} isPending={contacts.isPending} />
        )}
      </div>
    </div>
  )
}

function Tab({
  id,
  label,
  active,
  onSelect,
}: {
  id: 'deals' | 'contacts'
  label: string
  active: boolean
  onSelect: (id: 'deals' | 'contacts') => void
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => onSelect(id)}
      className={cn(
        'border-b-2 py-2.5 text-base text-ink-gray-5 hover:text-ink-gray-8',
        active ? 'border-ink-gray-8 font-medium text-ink-gray-8' : 'border-transparent',
      )}
    >
      {label}
    </button>
  )
}

function DealList({
  rows,
  isPending,
}: {
  rows: Record<string, unknown>[]
  isPending: boolean
}) {
  const { getStatus } = useStatuses('CRM Deal Status')

  if (isPending) return <Empty text="Loading…" />
  if (!rows.length) return <Empty text="No deals with this organization yet." />

  return (
    <ul className="divide-y divide-outline-gray-1">
      {rows.map((row) => (
        <li key={String(row.name)}>
          <Link
            to="/deals/$dealId"
            params={{ dealId: String(row.name) }}
            className="flex items-center gap-3 py-2.5 hover:bg-surface-gray-1"
          >
            <span
              aria-hidden
              className="h-2 w-2 shrink-0 rounded-full"
              style={{
                backgroundColor: getStatus(String(row.status ?? ''))?.color ?? '#cbd5e1',
              }}
            />
            <div className="min-w-0 flex-1">
              <div className="truncate text-base text-ink-gray-8">
                {formatCurrency(row.deal_value, (row.currency as string) || undefined)}
              </div>
              <div className="text-sm text-ink-gray-5">{String(row.status ?? '')}</div>
            </div>
            <span className="shrink-0 text-sm text-ink-gray-4">{timeAgo(row.modified)}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function ContactList({
  rows,
  isPending,
}: {
  rows: Record<string, unknown>[]
  isPending: boolean
}) {
  if (isPending) return <Empty text="Loading…" />
  if (!rows.length) return <Empty text="Nobody here works for this organization yet." />

  return (
    <ul className="divide-y divide-outline-gray-1">
      {rows.map((row) => (
        <li key={String(row.name)}>
          <Link
            to="/contacts/$contactId"
            params={{ contactId: String(row.name) }}
            className="flex items-center gap-3 py-2.5 hover:bg-surface-gray-1"
          >
            <Avatar
              image={row.image as string}
              label={String(row.full_name ?? row.name)}
              size="md"
            />
            <div className="min-w-0 flex-1">
              <div className="truncate text-base text-ink-gray-8">
                {String(row.full_name ?? row.name)}
              </div>
              <div className="truncate text-sm text-ink-gray-5">
                {String(row.email_id ?? row.mobile_no ?? '')}
              </div>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function Empty({ text }: { text: string }) {
  return <p className="py-10 text-center text-base text-ink-gray-4">{text}</p>
}
