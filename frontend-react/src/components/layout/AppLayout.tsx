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

/**
 * The signed-in chrome: a sidebar and the routed page.
 *
 * Deliberately thin. The Vue `AppSidebar.vue` carries notifications, a doctype switcher,
 * pinned views and the telephony widget; none of those screens exist yet, and stubbing
 * them here would be inventing an abstraction for callers that do not exist.
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
        <nav className="flex flex-col gap-1">
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
            </Link>
          ))}
        </nav>

        <div className="flex items-center justify-between gap-2 px-1">
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
