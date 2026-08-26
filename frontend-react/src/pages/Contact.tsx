import { useParams } from '@tanstack/react-router'
import { RecordScreen } from '@/record/RecordScreen'

/**
 * One contact. No `statusDoctype`: a contact has no status.
 *
 * The second data point on what a record screen costs once `RecordScreen` exists.
 */
export function ContactPage() {
  const { contactId } = useParams({ from: '/authed/contacts/$contactId' })

  return (
    <RecordScreen
      key={contactId}
      doctype="Contact"
      name={contactId}
      titleField="name"
      backTo="/contacts/view"
      backLabel="Contacts"
    />
  )
}
