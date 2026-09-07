import { useEffect, useState } from 'react'
import { Link, Outlet, useNavigate, useRouterState } from '@tanstack/react-router'
import {
  Bell,
  Briefcase,
  Building2,
  CheckSquare,
  Contact,
  LayoutDashboard,
  LogOut,
  Menu,
  Phone,
  Settings,
  StickyNote,
  Users,
} from 'lucide-react'
import { useSession } from '@/auth/session'
import { Avatar } from '@/components/ui/primitives'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { CallPanel } from '@/telephony/CallPanel'
import { SidebarViews } from './SidebarViews'
import { UnreadBadge } from './UnreadBadge'

/**
 * The signed-in chrome: a sidebar and the routed page.
 *
 * `AppSidebar.vue` is 729 lines. This is the part of it that carries its weight —
 * navigation, the saved views a user has pinned or published, and the live call panel.
 * Still not ported: collapsing the sidebar to icons, the demo-data reset, the help menu.
 *
 * **One layout, not two.** The Vue app has a `DesktopLayout` and a `MobileLayout` with a
 * `MobileSidebar` and a `MobileAppHeader` beside the desktop ones, and separate
 * `MobileDeal` / `MobileLead` / `MobileContact` pages. That is a Vue-era answer to a problem
 * Tailwind's breakpoints solve in one tree, and maintaining two of every screen is how they
 * drift. Below `lg` the sidebar becomes a drawer over the content; everything else is the
 * same components at a different width.
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
  const [drawerOpen, setDrawerOpen] = useState(false)

  // Navigating is what closes the drawer — a tap on a link should not also need a tap on
  // the backdrop. The desktop sidebar is unaffected because it is never in drawer state.
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  useEffect(() => setDrawerOpen(false), [pathname])

  async function signOut() {
    await logout()
    navigate({ to: '/login' })
  }

  return (
    <div className="flex h-screen bg-surface-white">
      {drawerOpen ? (
        <button
          type="button"
          aria-label="Close menu"
          className="fixed inset-0 z-20 bg-black/30 lg:hidden"
          onClick={() => setDrawerOpen(false)}
        />
      ) : null}

      <aside
        className={cn(
          'flex w-52 shrink-0 flex-col justify-between border-r border-outline-gray-1 bg-surface-gray-1 p-2',
          // Off-canvas below `lg`, in the flow above it. `fixed` rather than a width
          // transition so the main column never reflows as it slides.
          'fixed inset-y-0 left-0 z-30 transition-transform lg:static lg:translate-x-0',
          drawerOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
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
        {/* The only chrome that exists solely for small screens. `MobileAppHeader.vue`'s
            job, and all of it: somewhere to put the menu button. */}
        <div className="flex shrink-0 items-center gap-2 border-b border-outline-gray-1 px-2 py-1.5 lg:hidden">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Open menu"
            onClick={() => setDrawerOpen(true)}
          >
            <Menu className="h-4 w-4" />
          </Button>
          <span className="text-base font-semibold text-ink-gray-8">Frappe CRM</span>
        </div>

        <Outlet />
      </main>

      {/* A call arrives without anyone clicking, so its panel cannot live on a route. */}
      <CallPanel />
    </div>
  )
}
