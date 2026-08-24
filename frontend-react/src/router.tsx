import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from '@tanstack/react-router'
import { isAuthenticated } from '@/auth/tokens'
import { AppLayout } from '@/components/layout/AppLayout'
import { AcceptInvitationPage } from '@/pages/auth/AcceptInvitation'
import { ForgotPasswordPage } from '@/pages/auth/ForgotPassword'
import { LoginPage } from '@/pages/auth/Login'
import { UpdatePasswordPage } from '@/pages/auth/UpdatePassword'
import { CallLogsPage } from '@/pages/CallLogs'
import { ContactsPage } from '@/pages/Contacts'
import { DealsPage } from '@/pages/Deals'
import { LeadsPage } from '@/pages/Leads'
import { NotesPage } from '@/pages/Notes'
import { OrganizationsPage } from '@/pages/Organizations'
import { TasksPage } from '@/pages/Tasks'

/**
 * Routes. The Vue app's `router.js`, minus what this conversion has not reached yet.
 *
 * Code-based rather than file-based routing: both are first-class in TanStack Router,
 * and code-based keeps the whole route table — including the auth guard — readable in
 * one file, with no generated `routeTree.gen.ts` to review.
 *
 * The Vue app is served under `/crm` (`createWebHistory('/crm')`) because Frappe mounts
 * it there. This one is served at the root by Vite, so the paths below are bare.
 */

export type RouterContext = {
  /**
   * Read at navigation time, from token storage rather than React state — see
   * `isAuthenticated`. A guard reading state navigates on the pre-login value.
   */
  isLoggedIn: () => boolean
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
})

/**
 * The auth screens render for someone with no account, so they bypass the guard
 * entirely. A signed-in visitor on `/login` is sent home instead: a login form for
 * someone already logged in is a way to end up with two sessions and no clear idea which
 * is current. Both rules are ported from `router.js:190-197`.
 */
const publicRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'public',
  component: Outlet,
})

const loginRoute = createRoute({
  getParentRoute: () => publicRoute,
  path: '/login',
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => {
    // Only a path, never a full URL. `redirect` comes from the query string, so a caller
    // can put anything there, and accepting `https://elsewhere.example/` would make the
    // login page an open redirect — a phishing link that really does log you in and then
    // lands you somewhere else. Ported from `stores/session.js:55-58`.
    const value = search.redirect
    return typeof value === 'string' && /^\/(?!\/)/.test(value) ? { redirect: value } : {}
  },
  beforeLoad: ({ context }) => {
    if (context.isLoggedIn()) throw redirect({ to: '/deals/view' })
  },
  component: LoginPage,
})

const forgotPasswordRoute = createRoute({
  getParentRoute: () => publicRoute,
  path: '/forgot-password',
  component: ForgotPasswordPage,
})

const updatePasswordRoute = createRoute({
  getParentRoute: () => publicRoute,
  path: '/update-password',
  validateSearch: (search: Record<string, unknown>) => ({
    key: typeof search.key === 'string' ? search.key : '',
  }),
  component: UpdatePasswordPage,
})

const acceptInvitationRoute = createRoute({
  getParentRoute: () => publicRoute,
  path: '/accept-invitation',
  validateSearch: (search: Record<string, unknown>) => ({
    key: typeof search.key === 'string' ? search.key : '',
  }),
  component: AcceptInvitationPage,
})

/** Everything below here needs a session. */
const authedRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'authed',
  beforeLoad: ({ context, location }) => {
    if (!context.isLoggedIn()) {
      // `redirect` in the search string, matching the Vue guard, so Login can send them
      // back to whatever they were reaching for.
      throw redirect({ to: '/login', search: { redirect: location.href } })
    }
  },
  component: AppLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/',
  beforeLoad: () => {
    throw redirect({ to: '/deals/view' })
  },
})

/**
 * `viewType` is optional in the Vue routes (`/deals/view/:viewType?`). TanStack Router
 * has no optional path segment, so each list screen is two routes pointing at one
 * component — which is what keeps `/deals/view` and `/deals/view/kanban` both valid.
 *
 * Seven screens need that pair, so it is written once. (Two would not have justified a
 * helper; seven do.)
 */
function listRoutes<TPath extends string>(
  basePath: TPath,
  component: () => JSX.Element,
) {
  return [
    createRoute({
      getParentRoute: () => authedRoute,
      path: basePath,
      validateSearch: viewSearch,
      component,
    }),
    createRoute({
      getParentRoute: () => authedRoute,
      path: `${basePath}/$viewType` as const,
      validateSearch: viewSearch,
      component,
    }),
  ] as const
}

/** `?view=<saved view name>`, the same query param the Vue app uses. */
function viewSearch(search: Record<string, unknown>): { view?: string } {
  return typeof search.view === 'string' ? { view: search.view } : {}
}

const listScreenRoutes = [
  ...listRoutes('/deals/view', DealsPage),
  ...listRoutes('/leads/view', LeadsPage),
  ...listRoutes('/contacts/view', ContactsPage),
  ...listRoutes('/organizations/view', OrganizationsPage),
  ...listRoutes('/notes/view', NotesPage),
  ...listRoutes('/tasks/view', TasksPage),
  ...listRoutes('/call-logs/view', CallLogsPage),
]

const routeTree = rootRoute.addChildren([
  publicRoute.addChildren([
    loginRoute,
    forgotPasswordRoute,
    updatePasswordRoute,
    acceptInvitationRoute,
  ]),
  authedRoute.addChildren([indexRoute, ...listScreenRoutes]),
])

export const router = createRouter({
  routeTree,
  context: { isLoggedIn: isAuthenticated },
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
