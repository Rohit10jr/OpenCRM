import { useParams, useSearch } from '@tanstack/react-router'
import { ListView } from '@/list/ListView'

/**
 * Tasks. Offers kanban (`Tasks.vue:27`).
 *
 * No `statusDoctype`: a task's status is a Select field on the model rather than rows in
 * a `* Status` doctype, so there are no colours to look up and the kanban columns come
 * from the field's choices (`_kanban`, doc.py:449).
 */
export function TasksPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })

  return (
    <ListView
      doctype="CRM Task"
      title="Tasks"
      basePath="/tasks/view"
      viewType={viewType}
      savedViewName={view}
      allowedViews={['list', 'kanban']}
      kanbanTitleField="title"
    />
  )
}
