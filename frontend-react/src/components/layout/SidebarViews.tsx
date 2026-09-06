import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { Globe, Pin } from 'lucide-react'
import { callGet } from '@/api/client'
import type { SavedView } from '@/api/types'

/**
 * The Pinned Views and Public Views sections of the sidebar — `AppSidebar.vue:296-331`.
 *
 * This is what pinning is *for*. Run 4 wired the pin and publish endpoints, run 5 gave them
 * buttons in the view picker, and until this the result was invisible the moment you left
 * the list you pinned from.
 *
 * `crm.api.views.get_views` takes a doctype and returns every view when given none
 * (`views.py:31`), which is exactly the cross-doctype list a sidebar wants. The rows carry
 * `route_name` — the Vue router's route name, e.g. `Deals` — so that has to be mapped to a
 * path here. An unrecognised one is skipped rather than guessed: a sidebar link that 404s
 * is worse than a sidebar with one fewer entry.
 */
export function SidebarViews() {
  const views = useQuery({
    queryKey: ['views', 'all'],
    queryFn: () => callGet<SavedView[]>('crm.api.views.get_views', { doctype: '' }),
    retry: false,
  })

  const all = views.data ?? []
  const pinned = all.filter((view) => view.pinned)
  const publicViews = all.filter((view) => view.public && !view.pinned)

  if (!pinned.length && !publicViews.length) return null

  return (
    <>
      <ViewGroup label="Pinned" icon={Pin} views={pinned} />
      <ViewGroup label="Public" icon={Globe} views={publicViews} />
    </>
  )
}

function ViewGroup({
  label,
  icon: Icon,
  views,
}: {
  label: string
  icon: typeof Pin
  views: SavedView[]
}) {
  const links = views
    .map((view) => ({ view, path: pathFor(view.route_name) }))
    .filter((entry): entry is { view: SavedView; path: string } => Boolean(entry.path))

  if (!links.length) return null

  return (
    <div className="mt-3">
      <div className="flex items-center gap-1.5 px-2 py-1 text-sm font-medium uppercase tracking-wide text-ink-gray-4">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      {links.map(({ view, path }) => (
        <Link
          key={view.name}
          to={path}
          search={{ view: String(view.name) }}
          className="flex items-center gap-2 rounded px-2 py-1.5 text-sm text-ink-gray-7 hover:bg-surface-gray-2"
          activeProps={{ className: 'bg-surface-gray-3 font-medium' }}
        >
          <span className="truncate">{view.label || view.name}</span>
        </Link>
      ))}
    </div>
  )
}

/**
 * `route_name` is a Vue router route name, stored on the row by whichever client saved it.
 * The two clients share a database, so these strings arrive from the Vue app as well.
 */
const ROUTES: Record<string, string> = {
  Leads: '/leads/view',
  Deals: '/deals/view',
  Contacts: '/contacts/view',
  Organizations: '/organizations/view',
  Notes: '/notes/view',
  Tasks: '/tasks/view',
  'Call Logs': '/call-logs/view',
}

function pathFor(routeName: string | undefined): string | undefined {
  return routeName ? ROUTES[routeName] : undefined
}
