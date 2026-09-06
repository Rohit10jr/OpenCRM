import { useParams } from '@tanstack/react-router'
import { LinkedDeals } from '@/record/LinkedDeals'
import { RecordScreen } from '@/record/RecordScreen'

/**
 * One contact. No `statusDoctype`: a contact has no status.
 *
 * The second data point on what a record screen costs once `RecordScreen` exists.
 *
 * The deals list is the one thing a contact has that the shared screen cannot derive: a
 * contact is not linked to deals by a field, but through `CRM Contacts` rows, and only
 * `get_linked_deals` knows how to walk that.
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
      asideTop={<LinkedDeals contactId={contactId} />}
    />
  )
}
