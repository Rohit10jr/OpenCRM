import { useParams } from '@tanstack/react-router'
import { RecordScreen } from '@/record/RecordScreen'

/** One lead. The fourth record screen, and the second with an activity feed. */
export function LeadPage() {
  const { leadId } = useParams({ from: '/authed/leads/$leadId' })

  return (
    <RecordScreen
      key={leadId}
      doctype="CRM Lead"
      name={leadId}
      statusDoctype="CRM Lead Status"
      titleField="lead_name"
      backTo="/leads/view"
      backLabel="Leads"
    />
  )
}
