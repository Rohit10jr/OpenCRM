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
      // Remount per record so no state carries across. Without it, opening a deal while
      // the Attachments tab is selected opens the *next* deal on Attachments too —
      // React's documented way to reset state when the identity of the thing changes.
      key={dealId}
      doctype="CRM Deal"
      name={dealId}
      statusDoctype="CRM Deal Status"
      titleField="organization"
      backTo="/deals/view"
      backLabel="Deals"
    />
  )
}
