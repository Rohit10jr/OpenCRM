import { useState } from 'react'
import { useParams, useSearch } from '@tanstack/react-router'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ListView } from '@/list/ListView'
import { CreateModal } from '@/record/CreateModal'

/**
 * Tasks. Offers kanban (`Tasks.vue:27`).
 *
 * No `statusDoctype`: a task's status is a Select field on the model rather than rows in a
 * `* Status` doctype, so there are no colours to look up and the kanban columns come from
 * the field's choices (`_kanban`, doc.py:449).
 */
export function TasksPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })
  const [creating, setCreating] = useState(false)

  return (
    <>
      <ListView
        doctype="CRM Task"
        title="Tasks"
        basePath="/tasks/view"
        viewType={viewType}
        savedViewName={view}
        allowedViews={['list', 'kanban']}
        kanbanTitleField="title"
        headerActions={
          <Button variant="solid" size="md" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            Create
          </Button>
        }
      />
      <CreateModal
        doctype="CRM Task"
        title="Task"
        open={creating}
        onOpenChange={setCreating}
      />
    </>
  )
}
