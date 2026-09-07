import { Link, Outlet } from '@tanstack/react-router'
import { cn } from '@/lib/utils'

/**
 * The settings shell: a section list on the left, the chosen page on the right.
 *
 * `Settings.vue` renders this as a modal over the app. Here it is a route
 * (`/settings/...`), because a modal that holds fifteen screens is a router with worse
 * ergonomics — you cannot link to a settings page, reload into one, or press back out of
 * one. The Vue app's own URL scheme agrees with that instinct: it already tracks the active
 * page in `activeSettingsPage`.
 */
export const SETTINGS_NAV = [
  {
    group: 'Your account',
    items: [
      { to: '/settings/profile', label: 'Profile' },
      { to: '/settings/preferences', label: 'Preferences' },
    ],
  },
  {
    group: 'Workspace',
    items: [
      { to: '/settings/general', label: 'General' },
      { to: '/settings/brand', label: 'Brand' },
      { to: '/settings/defaults', label: 'Defaults' },
      { to: '/settings/home-actions', label: 'Home actions' },
    ],
  },
  {
    group: 'People',
    items: [
      { to: '/settings/users', label: 'Users' },
      { to: '/settings/hierarchy', label: 'Sales hierarchy' },
      { to: '/settings/assignment-rules', label: 'Assignment rules' },
    ],
  },
  {
    group: 'Communication',
    items: [
      { to: '/settings/email-accounts', label: 'Email accounts' },
      { to: '/settings/email-templates', label: 'Email templates' },
      { to: '/settings/telephony', label: 'Telephony' },
      { to: '/settings/whatsapp', label: 'WhatsApp' },
    ],
  },
  {
    group: 'Integrations',
    items: [
      { to: '/settings/erpnext', label: 'ERPNext' },
      { to: '/settings/lead-syncing', label: 'Lead syncing' },
      { to: '/settings/sla', label: 'Service levels' },
    ],
  },
] as const

export function SettingsLayout() {
  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row">
      {/* A row of chips above the content on a phone, a column beside it on a desktop. */}
      <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-outline-gray-1 bg-surface-gray-1 p-2 md:w-56 md:flex-col md:overflow-y-auto md:border-b-0 md:border-r md:p-3">
        <h1 className="mb-3 hidden px-2 text-lg font-semibold text-ink-gray-8 md:block">Settings</h1>
        {SETTINGS_NAV.map((section) => (
          <div key={section.group} className="flex gap-1 md:mb-4 md:flex-col">
            <p className="mb-1 hidden px-2 text-sm font-medium text-ink-gray-5 md:block">
              {section.group}
            </p>
            {section.items.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="block whitespace-nowrap rounded px-2 py-1.5 text-base text-ink-gray-7 hover:bg-surface-gray-2"
                activeProps={{ className: 'bg-surface-gray-3 font-medium text-ink-gray-8' }}
              >
                {item.label}
              </Link>
            ))}
          </div>
        ))}
      </nav>

      <div className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </div>
    </div>
  )
}

/** The heading every settings page shares, so they do not each invent one. */
export function SettingsPage({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string
  description?: string
  actions?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('mx-auto max-w-3xl p-6', className)}>
      <header className="mb-5 flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-ink-gray-8">{title}</h2>
          {description ? (
            <p className="mt-1 text-base text-ink-gray-5">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </header>
      {children}
    </div>
  )
}
