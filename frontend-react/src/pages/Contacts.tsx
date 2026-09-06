import { useState } from 'react'
import { useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ListView } from '@/list/ListView'
import { CreateModal } from '@/record/CreateModal'

/**
 * Contacts. `Contact` is a Frappe core doctype rather than a CRM one, which is why the
 * doctype name has no prefix — the same distinction the Vue page carries
 * (`Contacts.vue:25`).
 */
export function ContactsPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)

  return (
    <>
      <ListView
        doctype="Contact"
        title="Contacts"
        basePath="/contacts/view"
        viewType={viewType}
        savedViewName={view}
        onRowClick={(row) =>
          navigate({ to: '/contacts/$contactId', params: { contactId: row.name } })
        }
        headerActions={
          <Button variant="solid" size="md" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            Create
          </Button>
        }
      />
      <CreateModal
        doctype="Contact"
        title="Contact"
        open={creating}
        onOpenChange={setCreating}
        onCreated={(contactId) =>
          navigate({ to: '/contacts/$contactId', params: { contactId } })
        }
      />
    </>
  )
}
