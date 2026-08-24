import { useParams, useSearch } from '@tanstack/react-router'
import { ListView } from '@/list/ListView'
import { Avatar } from '@/components/ui/primitives'
import { useUsers } from '@/list/useLookups'

/**
 * Deals.
 *
 * `Deals.vue` is 562 lines plus a 312-line `DealsListView.vue`. Almost all of it is
 * row-parsing and kanban wiring that `ListView` now does for every doctype, so what is
 * left here is the three things that are genuinely about deals: which doctype holds its
 * statuses, which views it offers, and the one column the shared `Cell` cannot type from
 * the payload.
 *
 * If this file grows, that is a signal the engine is missing something — the fix is to
 * push it down into `list/`, not to widen this file.
 */
export function DealsPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })
  const { getUser } = useUsers()

  return (
    <ListView
      doctype="CRM Deal"
      title="Deals"
      basePath="/deals/view"
      statusDoctype="CRM Deal Status"
      viewType={viewType}
      savedViewName={view}
      allowedViews={['list', 'kanban']}
      kanbanTitleField="organization"
      cellOverrides={{
        // `deal_owner` is a Link to User, but the payload types it `Data` for some
        // doctypes, so the generic Link-to-User branch in `Cell` does not always fire.
        // Naming it here is cheaper than second-guessing the fieldtype in shared code.
        deal_owner: (row) => {
          const value = row.deal_owner
          if (!value) return null
          const user = getUser(String(value))
          return (
            <span className="flex items-center gap-2 truncate">
              <Avatar image={user.user_image} label={user.full_name} size="sm" />
              <span className="truncate">{user.full_name}</span>
            </span>
          )
        },
      }}
    />
  )
}
