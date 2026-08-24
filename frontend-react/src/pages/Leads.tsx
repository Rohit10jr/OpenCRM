import { useParams, useSearch } from '@tanstack/react-router'
import { ListView } from '@/list/ListView'
import { Avatar } from '@/components/ui/primitives'
import { useUsers } from '@/list/useLookups'

/**
 * Leads. The second list screen, and the one the conversion estimate is taken from.
 *
 * Everything structural — filters, sort, columns, kanban, selection, load-more — comes
 * from `ListView`. What is left is the same four facts Deals supplies, with different
 * values: the doctype, its status doctype, the views it offers, and the `converted: 0`
 * filter the page imposes (`Leads.vue:26`), which is a *page* filter rather than a user
 * one and so cannot be cleared from the toolbar.
 */
export function LeadsPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })
  const { getUser } = useUsers()

  return (
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
      cellOverrides={{
        lead_owner: (row) => {
          const value = row.lead_owner
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
