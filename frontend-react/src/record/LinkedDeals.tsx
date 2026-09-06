import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { callGet } from '@/api/client'
import { formatCurrency } from '@/lib/format'
import { useStatuses } from '@/list/useLookups'

/**
 * The deals a contact appears on — `Contact.vue`'s deals tab.
 *
 * `crm.api.contact.get_linked_deals` is served, and it is **more careful than upstream**:
 * ours reads the deals through `fetch_rows`, so a deal the caller cannot see does not come
 * back, where upstream's `frappe.get_cached_doc` does not permission-filter at all
 * (`contact.py:44-49`). A contact you can legitimately read is therefore not a way to see
 * deal values from elsewhere in the sales hierarchy. The visible consequence is that two
 * users can open the same contact and see different numbers of deals; that is correct.
 */
export function LinkedDeals({ contactId }: { contactId: string }) {
  const { getStatus } = useStatuses('CRM Deal Status')

  const deals = useQuery({
    queryKey: ['contact-deals', contactId],
    queryFn: () =>
      callGet<LinkedDeal[]>('crm.api.contact.get_linked_deals', { contact: contactId }),
    retry: false,
  })

  const rows = deals.data ?? []

  if (deals.isPending) {
    return <p className="px-4 py-3 text-sm text-ink-gray-4">Loading deals…</p>
  }
  if (!rows.length) return null

  return (
    <section className="border-b border-outline-gray-1 px-4 py-3">
      <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-ink-gray-5">
        Deals ({rows.length})
      </h2>
      <ul className="flex flex-col gap-1">
        {rows.map((deal) => (
          <li key={deal.name}>
            <Link
              to="/deals/$dealId"
              params={{ dealId: deal.name }}
              className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-surface-gray-1"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-base text-ink-gray-8">
                  {deal.organization || deal.name}
                </div>
                <div className="text-sm text-ink-gray-5">
                  {/* `deal_value` is in the deal's own currency, which is why it comes
                      back alongside it — a workspace can hold deals in several. */}
                  {formatCurrency(deal.deal_value, deal.currency || 'USD')}
                </div>
              </div>
              {deal.status ? (
                <span className="flex shrink-0 items-center gap-1.5 text-sm text-ink-gray-6">
                  {/* The status doctype stores an arbitrary colour and `Badge` knows five
                      themes, so the dot carries the colour and the text carries the name. */}
                  <span
                    aria-hidden
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: getStatus(deal.status)?.color ?? '#cbd5e1' }}
                  />
                  {deal.status}
                </span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

type LinkedDeal = {
  name: string
  organization?: string
  currency?: string
  deal_value?: number
  status?: string
  email?: string
  mobile_no?: string
  deal_owner?: string
}
