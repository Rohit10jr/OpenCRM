import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from '@tanstack/react-router'
import { AppLayout } from '@/components/layout/AppLayout'
import { AcceptInvitationPage } from '@/pages/auth/AcceptInvitation'
import { ForgotPasswordPage } from '@/pages/auth/ForgotPassword'
import { LoginPage } from '@/pages/auth/Login'
import { UpdatePasswordPage } from '@/pages/auth/UpdatePassword'
import { DealsPage } from '@/pages/Deals'
import { LeadsPage } from '@/pages/Leads'

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
  /** Read at navigation time so the guard sees the *current* session, not a stale copy. */
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
 * has no optional path segment, so it is two routes pointing at one component — which is
 * also what makes `/deals/view` and `/deals/view/kanban` both valid URLs, as before.
 */
const dealsRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/deals/view',
  validateSearch: viewSearch,
  component: DealsPage,
})

const dealsViewTypeRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/deals/view/$viewType',
  validateSearch: viewSearch,
  component: DealsPage,
})

const leadsRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/leads/view',
  validateSearch: viewSearch,
  component: LeadsPage,
})

const leadsViewTypeRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/leads/view/$viewType',
  validateSearch: viewSearch,
  component: LeadsPage,
})

/** `?view=<saved view name>`, the same query param the Vue app uses. */
function viewSearch(search: Record<string, unknown>): { view?: string } {
  return typeof search.view === 'string' ? { view: search.view } : {}
}

const routeTree = rootRoute.addChildren([
  publicRoute.addChildren([
    loginRoute,
    forgotPasswordRoute,
    updatePasswordRoute,
    acceptInvitationRoute,
  ]),
  authedRoute.addChildren([
    indexRoute,
    dealsRoute,
    dealsViewTypeRoute,
    leadsRoute,
    leadsViewTypeRoute,
  ]),
])

export const router = createRouter({
  routeTree,
  // Replaced in `App.tsx` with one that reads live session state. A router needs its
  // context at construction, and the session only exists inside React.
  context: { isLoggedIn: () => false },
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
