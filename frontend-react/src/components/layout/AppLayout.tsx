import { Link, Outlet, useNavigate } from '@tanstack/react-router'
import {
  Bell,
  Briefcase,
  Building2,
  CheckSquare,
  Contact,
  LayoutDashboard,
  LogOut,
  Phone,
  Settings,
  StickyNote,
  Users,
} from 'lucide-react'
import { useSession } from '@/auth/session'
import { Avatar } from '@/components/ui/primitives'
import { Button } from '@/components/ui/button'
import { CallPanel } from '@/telephony/CallPanel'
import { SidebarViews } from './SidebarViews'
import { UnreadBadge } from './UnreadBadge'

/**
 * The signed-in chrome: a sidebar and the routed page.
 *
 * `AppSidebar.vue` is 729 lines. This is the part of it that carries its weight —
 * navigation, the saved views a user has pinned or published, and the live call panel.
 * Still not ported: collapsing the sidebar, the demo-data reset, and the help menu.
 */
const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/notifications', label: 'Notifications', icon: Bell },
  { to: '/leads/view', label: 'Leads', icon: Users },
  { to: '/deals/view', label: 'Deals', icon: Briefcase },
  { to: '/contacts/view', label: 'Contacts', icon: Contact },
  { to: '/organizations/view', label: 'Organizations', icon: Building2 },
  { to: '/notes/view', label: 'Notes', icon: StickyNote },
  { to: '/tasks/view', label: 'Tasks', icon: CheckSquare },
  { to: '/call-logs/view', label: 'Call Logs', icon: Phone },
  { to: '/settings/profile', label: 'Settings', icon: Settings },
] as const

export function AppLayout() {
  const { user, logout } = useSession()
  const navigate = useNavigate()

  async function signOut() {
    await logout()
    navigate({ to: '/login' })
  }

  return (
    <div className="flex h-screen bg-surface-white">
      <aside className="flex w-52 shrink-0 flex-col justify-between border-r border-outline-gray-1 bg-surface-gray-1 p-2">
        <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
          <div className="mb-2 px-2 py-1 text-base font-semibold text-ink-gray-8">
            Frappe CRM
          </div>
          {NAV.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              className="flex items-center gap-2 rounded px-2 py-1.5 text-base text-ink-gray-7 hover:bg-surface-gray-2"
              activeProps={{ className: 'bg-surface-gray-3 font-medium' }}
            >
              <Icon className="h-4 w-4" />
              {label}
              {to === '/notifications' ? <UnreadBadge /> : null}
            </Link>
          ))}

          <SidebarViews />
        </nav>

        <div className="mt-2 flex shrink-0 items-center justify-between gap-2 px-1">
          <div className="flex min-w-0 items-center gap-2">
            <Avatar label={user} size="md" />
            <span className="truncate text-sm text-ink-gray-6">{user}</span>
          </div>
          <Button variant="ghost" size="icon" onClick={signOut} title="Sign out">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>

      {/* A call arrives without anyone clicking, so its panel cannot live on a route. */}
      <CallPanel />
    </div>
  )
}
