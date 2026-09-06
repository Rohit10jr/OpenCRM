import { useState } from 'react'
import { useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ListView } from '@/list/ListView'
import { CreateModal } from '@/record/CreateModal'

export function OrganizationsPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)

  return (
    <>
      <ListView
        doctype="CRM Organization"
        title="Organizations"
        basePath="/organizations/view"
        viewType={viewType}
        savedViewName={view}
        onRowClick={(row) =>
          navigate({
            to: '/organizations/$organizationId',
            params: { organizationId: row.name },
          })
        }
        headerActions={
          <Button variant="solid" size="md" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            Create
          </Button>
        }
      />
      <CreateModal
        doctype="CRM Organization"
        title="Organization"
        open={creating}
        onOpenChange={setCreating}
        onCreated={(organizationId) =>
          navigate({ to: '/organizations/$organizationId', params: { organizationId } })
        }
      />
    </>
  )
}
