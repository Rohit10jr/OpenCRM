/**
 * The shell the four auth screens share.
 *
 * Deliberately not the app chrome: no sidebar, no user dropdown, nothing that reads a
 * session. These render for someone who has no account yet.
 */
export function AuthLayout({
  title,
  subtitle,
  footer,
  children,
}: {
  title: string
  subtitle?: string
  footer?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-surface-gray-1 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-semibold text-ink-gray-9">{title}</h1>
          {subtitle ? <p className="mt-2 text-base text-ink-gray-5">{subtitle}</p> : null}
        </div>

        <div className="rounded-lg border border-outline-gray-1 bg-surface-white p-6 shadow-sm">
          {children}
        </div>

        {footer ? (
          <div className="mt-4 text-center text-sm text-ink-gray-5">{footer}</div>
        ) : null}
      </div>
    </div>
  )
}
