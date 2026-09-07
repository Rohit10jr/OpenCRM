import { useParams } from '@tanstack/react-router'
import { RecordScreen } from '@/record/RecordScreen'
import { RelatedLists } from '@/record/RelatedLists'

/**
 * One organization. The third data point on the record-screen cost.
 *
 * An organization has no activity feed, so until this it showed a side panel and the
 * sentence "this doctype has no activity feed". True, and useless — what an organization
 * *is*, in this CRM, is the deals and people attached to it.
 */
export function OrganizationPage() {
  const { organizationId } = useParams({ from: '/authed/organizations/$organizationId' })

  return (
    <RecordScreen
      key={organizationId}
      doctype="CRM Organization"
      name={organizationId}
      titleField="organization_name"
      backTo="/organizations/view"
      backLabel="Organizations"
      body={<RelatedLists organizationId={organizationId} />}
    />
  )
}
