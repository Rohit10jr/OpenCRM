import { useState } from 'react'
import { useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { userCell } from '@/list/Cell'
import { ListView } from '@/list/ListView'
import { useUsers } from '@/list/useLookups'
import { CreateModal } from '@/record/CreateModal'

/**
 * Leads. The second list screen, and the one run 1's conversion estimate came from.
 *
 * Everything structural — filters, sort, columns, kanban, selection, load-more, saved
 * views — comes from `ListView`. What is left is the same handful of facts Deals supplies
 * with different values, plus the `converted: 0` filter the page imposes
 * (`Leads.vue:26`), which is a *page* filter rather than a user one and so cannot be
 * cleared from the toolbar.
 */
export function LeadsPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })
  const { getUser } = useUsers()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)

  return (
    <>
      <ListView
        doctype="CRM Lead"
        title="Leads"
        basePath="/leads/view"
        statusDoctype="CRM Lead Status"
        viewType={viewType}
        savedViewName={view}
        allowedViews={['list', 'group_by', 'kanban']}
        kanbanTitleField="lead_name"
        defaultFilters={{ converted: 0 }}
        onRowClick={(row) => navigate({ to: '/leads/$leadId', params: { leadId: row.name } })}
        cellOverrides={{ lead_owner: userCell(getUser) }}
        headerActions={
          <Button variant="solid" size="md" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            Create
          </Button>
        }
      />
      <CreateModal
        doctype="CRM Lead"
        title="Lead"
        open={creating}
        onOpenChange={setCreating}
        onCreated={(leadId) => navigate({ to: '/leads/$leadId', params: { leadId } })}
      />
    </>
  )
}
