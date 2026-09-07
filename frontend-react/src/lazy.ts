import { lazyRouteComponent } from '@tanstack/react-router'

/**
 * Route components that are loaded on demand.
 *
 * **The bundle went from 573 kB to 1.1 MB when TipTap landed**, and run 3 had already
 * flagged the single chunk as a weakness getting worse each run. This is the fix, and it is
 * cheap because the split lines are obvious: nobody opens the settings, the dashboard or a
 * data import on their way to a deal list, and the editor only exists inside a record.
 *
 * Split by *when a screen is first reached*, not by size:
 *
 * * **Eager** — login, the app shell, list screens and record screens. These are the first
 *   thing anyone sees, and lazy-loading the landing screen buys a spinner, not a saving.
 * * **Lazy** — everything below.
 *
 * `lazyRouteComponent` is TanStack Router's own wrapper: it preloads on hover and on intent,
 * so the chunk is usually already there by the time the click lands. Plain `React.lazy`
 * would work but would make every navigation wait.
 */

export const LazyDashboard = lazyRouteComponent(
  () => import('@/pages/Dashboard'),
  'DashboardPage',
)
export const LazyNotifications = lazyRouteComponent(
  () => import('@/pages/Notifications'),
  'NotificationsPage',
)
export const LazyDataImport = lazyRouteComponent(
  () => import('@/pages/DataImport'),
  'DataImportPage',
)
export const LazyWelcome = lazyRouteComponent(() => import('@/pages/Welcome'), 'WelcomePage')

export const LazySettingsLayout = lazyRouteComponent(
  () => import('@/pages/settings/SettingsLayout'),
  'SettingsLayout',
)
export const LazyProfile = lazyRouteComponent(
  () => import('@/pages/settings/Profile'),
  'ProfileSettingsPage',
)
export const LazyUsers = lazyRouteComponent(
  () => import('@/pages/settings/Users'),
  'UsersSettingsPage',
)
export const LazyTelephony = lazyRouteComponent(
  () => import('@/pages/settings/Telephony'),
  'TelephonySettingsPage',
)
export const LazyAssignmentRules = lazyRouteComponent(
  () => import('@/pages/settings/AssignmentRules'),
  'AssignmentRulesSettingsPage',
)

export const LazyGeneral = lazyRouteComponent(
  () => import('@/pages/settings/Workspace'),
  'GeneralSettingsPage',
)
export const LazyBrand = lazyRouteComponent(
  () => import('@/pages/settings/Workspace'),
  'BrandSettingsPage',
)
export const LazyDefaults = lazyRouteComponent(
  () => import('@/pages/settings/Workspace'),
  'DefaultsSettingsPage',
)
export const LazyPreferences = lazyRouteComponent(
  () => import('@/pages/settings/Workspace'),
  'PreferencesSettingsPage',
)

export const LazyWhatsApp = lazyRouteComponent(
  () => import('@/pages/settings/Integrations'),
  'WhatsAppSettingsPage',
)
export const LazyERPNext = lazyRouteComponent(
  () => import('@/pages/settings/Integrations'),
  'ERPNextSettingsPage',
)

export const LazyEmailAccounts = lazyRouteComponent(
  () => import('@/pages/settings/Lists'),
  'EmailAccountsSettingsPage',
)
// Its own file, not `Lists` — a template's body needs a rich-text editor, which is the one
// thing the shared list-and-dialog cannot give it.
export const LazyEmailTemplates = lazyRouteComponent(
  () => import('@/pages/settings/EmailTemplates'),
  'EmailTemplatesSettingsPage',
)
export const LazySla = lazyRouteComponent(
  () => import('@/pages/settings/Lists'),
  'SlaSettingsPage',
)
export const LazyHierarchy = lazyRouteComponent(
  () => import('@/pages/settings/Lists'),
  'HierarchySettingsPage',
)
export const LazyLeadSyncing = lazyRouteComponent(
  () => import('@/pages/settings/Lists'),
  'LeadSyncingSettingsPage',
)
export const LazyHomeActions = lazyRouteComponent(
  () => import('@/pages/settings/Lists'),
  'HomeActionsSettingsPage',
)
