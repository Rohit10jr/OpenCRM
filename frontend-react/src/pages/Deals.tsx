import { useState } from 'react'
import { useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { userCell } from '@/list/Cell'
import { ListView } from '@/list/ListView'
import { useUsers } from '@/list/useLookups'
import { CreateModal } from '@/record/CreateModal'

/**
 * Deals.
 *
 * `Deals.vue` is 562 lines plus a 312-line `DealsListView.vue`. Almost all of it is
 * row-parsing and kanban wiring that `ListView` now does for every doctype, so what is
 * left here is the facts that are genuinely about deals: which doctype holds its
 * statuses, which views it offers, where a row goes when clicked, and the one column the
 * shared `Cell` cannot type from the payload.
 *
 * If this file grows, that is a signal the engine is missing something — the fix is to
 * push it down into `list/`, not to widen this file.
 */
export function DealsPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })
  const { getUser } = useUsers()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)

  return (
    <>
      <ListView
        doctype="CRM Deal"
        title="Deals"
        basePath="/deals/view"
        statusDoctype="CRM Deal Status"
        viewType={viewType}
        savedViewName={view}
        allowedViews={['list', 'group_by', 'kanban']}
        kanbanTitleField="organization"
        onRowClick={(row) => navigate({ to: '/deals/$dealId', params: { dealId: row.name } })}
        cellOverrides={{ deal_owner: userCell(getUser) }}
        headerActions={
          <Button variant="solid" size="md" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            Create
          </Button>
        }
      />
      <CreateModal
        doctype="CRM Deal"
        title="Deal"
        open={creating}
        onOpenChange={setCreating}
        onCreated={(dealId) => navigate({ to: '/deals/$dealId', params: { dealId } })}
      />
    </>
  )
}
