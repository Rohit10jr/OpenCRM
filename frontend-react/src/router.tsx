import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from '@tanstack/react-router'
import { isAuthenticated } from '@/auth/tokens'
import type { ListFilter } from '@/list/useListView'
import { AppLayout } from '@/components/layout/AppLayout'
import { AcceptInvitationPage } from '@/pages/auth/AcceptInvitation'
import { ForgotPasswordPage } from '@/pages/auth/ForgotPassword'
import { LoginPage } from '@/pages/auth/Login'
import { UpdatePasswordPage } from '@/pages/auth/UpdatePassword'
import { CallLogsPage } from '@/pages/CallLogs'
import { ContactPage } from '@/pages/Contact'
import { DashboardPage } from '@/pages/Dashboard'
import { DataImportPage } from '@/pages/DataImport'
import { NotificationsPage } from '@/pages/Notifications'
import { InvalidPage, NotPermittedPage, WelcomePage } from '@/pages/Welcome'
import { ContactsPage } from '@/pages/Contacts'
import { DealPage } from '@/pages/Deal'
import { DealsPage } from '@/pages/Deals'
import { LeadPage } from '@/pages/Lead'
import { LeadsPage } from '@/pages/Leads'
import { NotesPage } from '@/pages/Notes'
import { OrganizationPage } from '@/pages/Organization'
import { OrganizationsPage } from '@/pages/Organizations'
import { AssignmentRulesSettingsPage } from '@/pages/settings/AssignmentRules'
import {
  ERPNextSettingsPage,
  WhatsAppSettingsPage,
} from '@/pages/settings/Integrations'
import {
  EmailAccountsSettingsPage,
  EmailTemplatesSettingsPage,
  HierarchySettingsPage,
  HomeActionsSettingsPage,
  LeadSyncingSettingsPage,
  SlaSettingsPage,
} from '@/pages/settings/Lists'
import { ProfileSettingsPage } from '@/pages/settings/Profile'
import { SettingsLayout } from '@/pages/settings/SettingsLayout'
import { TelephonySettingsPage } from '@/pages/settings/Telephony'
import { UsersSettingsPage } from '@/pages/settings/Users'
import {
  BrandSettingsPage,
  DefaultsSettingsPage,
  GeneralSettingsPage,
  PreferencesSettingsPage,
} from '@/pages/settings/Workspace'
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

/**
 * A list screen's query string: the saved view, plus the user's filters and sort.
 *
 * **Filters and sort are in the URL, not in component state.** They were state in run 1,
 * which meant a filtered list could not be linked, did not survive a reload, and — once
 * rows became clickable — was gone when the user came back from a record.
 *
 * `filters` is a JSON array because a filter is three values and there can be several;
 * spreading them across `field1=`/`op1=`/`value1=` would encode the same thing worse. A
 * malformed value is dropped rather than thrown on: it arrives from a URL a person may
 * have edited, and an unparseable filter should show an unfiltered list, not a crash.
 */
export type ListSearch = {
  view?: string
  filters?: ListFilter[]
  order_by?: string
  group_by?: string
}

function viewSearch(search: Record<string, unknown>): ListSearch {
  const out: ListSearch = {}
  if (typeof search.view === 'string') out.view = search.view
  if (typeof search.order_by === 'string') out.order_by = search.order_by
  if (typeof search.group_by === 'string') out.group_by = search.group_by

  const filters = parseFilters(search.filters)
  if (filters.length) out.filters = filters
  return out
}

function parseFilters(value: unknown): ListFilter[] {
  const raw = typeof value === 'string' ? safeParse(value) : value
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (entry): entry is ListFilter =>
      Boolean(entry) &&
      typeof entry === 'object' &&
      typeof (entry as ListFilter).fieldname === 'string' &&
      typeof (entry as ListFilter).operator === 'string' &&
      typeof (entry as ListFilter).value === 'string',
  )
}

function safeParse(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

/**
 * Record screens: `/deals/CRM-DEAL-2026-00006`, matching the Vue route shape.
 *
 * Not folded into a helper the way `listRoutes` is: three routes with different param
 * names and no shared search schema is not yet a pattern, and naming the param `$dealId`
 * rather than `$name` is what makes `useParams` read well in the page.
 */
const dealRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/deals/$dealId',
  component: DealPage,
})

const leadRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/leads/$leadId',
  component: LeadPage,
})

const contactRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/contacts/$contactId',
  component: ContactPage,
})

const organizationRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/organizations/$organizationId',
  component: OrganizationPage,
})

/**
 * Settings is a nested route with its own shell, not a modal.
 *
 * `Settings.vue` renders the whole thing as a dialog over the app and tracks the open page
 * in a store. That is a router with worse ergonomics: you cannot link to a settings page,
 * reload into one, or press back out of one. Here `/settings/*` is real navigation and
 * `SettingsLayout` owns the section list.
 */
const settingsRoute = createRoute({
  getParentRoute: () => authedRoute,
  id: 'settings',
  component: SettingsLayout,
})

const settingsChildren = (
  [
    ['/settings/profile', ProfileSettingsPage],
    ['/settings/preferences', PreferencesSettingsPage],
    ['/settings/general', GeneralSettingsPage],
    ['/settings/brand', BrandSettingsPage],
    ['/settings/defaults', DefaultsSettingsPage],
    ['/settings/home-actions', HomeActionsSettingsPage],
    ['/settings/users', UsersSettingsPage],
    ['/settings/hierarchy', HierarchySettingsPage],
    ['/settings/assignment-rules', AssignmentRulesSettingsPage],
    ['/settings/email-accounts', EmailAccountsSettingsPage],
    ['/settings/email-templates', EmailTemplatesSettingsPage],
    ['/settings/telephony', TelephonySettingsPage],
    ['/settings/whatsapp', WhatsAppSettingsPage],
    ['/settings/erpnext', ERPNextSettingsPage],
    ['/settings/lead-syncing', LeadSyncingSettingsPage],
    ['/settings/sla', SlaSettingsPage],
  ] as const
).map(([path, component]) =>
  createRoute({ getParentRoute: () => settingsRoute, path, component }),
)

const welcomeRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/welcome',
  component: WelcomePage,
})

const notPermittedRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/not-permitted',
  component: NotPermittedPage,
})

const dataImportRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/data-import',
  component: DataImportPage,
})

/**
 * A single import's detail. The mapping UI is not built (`BACKEND_GAPS.md` §2), so this
 * route exists to be linked to from the history list and says as much.
 */
const dataImportDetailRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/data-import/$importName',
  component: DataImportPage,
})

const notificationsRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/notifications',
  component: NotificationsPage,
})

const dashboardRoute = createRoute({
  getParentRoute: () => authedRoute,
  path: '/dashboard',
  component: DashboardPage,
})

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
  authedRoute.addChildren([
    indexRoute,
    dealRoute,
    leadRoute,
    contactRoute,
    organizationRoute,
    notificationsRoute,
    dashboardRoute,
    welcomeRoute,
    notPermittedRoute,
    dataImportRoute,
    dataImportDetailRoute,
    settingsRoute.addChildren(settingsChildren),
    ...listScreenRoutes,
  ]),
])

export const router = createRouter({
  routeTree,
  context: { isLoggedIn: isAuthenticated },
  // Without this an unmatched URL renders nothing at all, which reads as a broken app
  // rather than a wrong address.
  defaultNotFoundComponent: InvalidPage,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
