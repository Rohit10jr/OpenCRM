import { useState } from 'react'
import { useParams, useSearch } from '@tanstack/react-router'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ListView } from '@/list/ListView'
import { CreateModal } from '@/record/CreateModal'

/**
 * `FCRM Note`, not `CRM Note` — the doctype really is spelled that way upstream.
 *
 * No row click: a note has no record screen of its own in either app. It is read in the
 * timeline of whatever it is attached to.
 */
export function NotesPage() {
  const { viewType } = useParams({ strict: false })
  const { view } = useSearch({ strict: false })
  const [creating, setCreating] = useState(false)

  return (
    <>
      <ListView
        doctype="FCRM Note"
        title="Notes"
        basePath="/notes/view"
        viewType={viewType}
        savedViewName={view}
        headerActions={
          <Button variant="solid" size="md" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            Create
          </Button>
        }
      />
      <CreateModal
        doctype="FCRM Note"
        title="Note"
        open={creating}
        onOpenChange={setCreating}
      />
    </>
  )
}
