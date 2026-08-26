import { useParams } from '@tanstack/react-router'
import { RecordScreen } from '@/record/RecordScreen'

/**
 * One deal.
 *
 * `Deal.vue` is 832 lines. What is left here is the same four facts a list page supplies:
 * the doctype, its status doctype, which field is the heading, and where "back" goes.
 * Everything structural is in `RecordScreen`, for the same reason the list engine is
 * shared — Contact and Organization are the next two callers.
 */
export function DealPage() {
  const { dealId } = useParams({ from: '/authed/deals/$dealId' })

  return (
    <RecordScreen
      doctype="CRM Deal"
      name={dealId}
      statusDoctype="CRM Deal Status"
      titleField="organization"
      backTo="/deals/view"
      backLabel="Deals"
    />
  )
}
