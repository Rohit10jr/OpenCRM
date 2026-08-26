import { useParams } from '@tanstack/react-router'
import { RecordScreen } from '@/record/RecordScreen'

/** One organization. The third data point on the record-screen cost. */
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
    />
  )
}
