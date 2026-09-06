import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { ArrowRight, Check, Circle } from 'lucide-react'
import { callGet } from '@/api/client'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/**
 * The first-run screen.
 *
 * `crm.api.onboarding.get_first_lead` and `get_first_deal` are served, and are exactly what
 * the Vue onboarding checks: has this workspace got anything in it yet. The steps below are
 * derived from those two answers rather than from a stored checklist, so the screen cannot
 * disagree with reality — tick a step by doing the thing.
 *
 * The persona wizard (`PersonaForm.vue`) is not built. It writes `persona_captured` on
 * `FCRM Settings` and branches the onboarding on the answer; that is a survey, and it is the
 * least useful thing on this list to convert.
 */
export function WelcomePage() {
  const navigate = useNavigate()

  const firstLead = useQuery({
    queryKey: ['onboarding', 'first-lead'],
    queryFn: () => callGet<unknown>('crm.api.onboarding.get_first_lead'),
    retry: false,
  })
  const firstDeal = useQuery({
    queryKey: ['onboarding', 'first-deal'],
    queryFn: () => callGet<unknown>('crm.api.onboarding.get_first_deal'),
    retry: false,
  })

  const steps = [
    {
      label: 'Create your first lead',
      done: Boolean(firstLead.data),
      to: '/leads/view' as const,
    },
    {
      label: 'Create your first deal',
      done: Boolean(firstDeal.data),
      to: '/deals/view' as const,
    },
    {
      label: 'Invite your team',
      // No endpoint says whether anyone has been invited, so this one stays open. Better an
      // honest permanent step than a tick that means nothing.
      done: false,
      to: '/settings/users' as const,
    },
  ]

  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="w-full max-w-lg">
        <h1 className="text-2xl font-semibold text-ink-gray-9">Welcome to Frappe CRM</h1>
        <p className="mt-1 text-base text-ink-gray-5">
          Three things worth doing before you start.
        </p>

        <ul className="mt-6 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-1">
          {steps.map((step) => (
            <li key={step.label}>
              <Link
                to={step.to}
                className="flex items-center gap-3 px-4 py-3 hover:bg-surface-gray-1"
              >
                {step.done ? (
                  <Check className="h-4 w-4 shrink-0 text-green-600" />
                ) : (
                  <Circle className="h-4 w-4 shrink-0 text-ink-gray-4" />
                )}
                <span
                  className={cn(
                    'flex-1 text-base',
                    step.done ? 'text-ink-gray-4 line-through' : 'text-ink-gray-8',
                  )}
                >
                  {step.label}
                </span>
                <ArrowRight className="h-4 w-4 shrink-0 text-ink-gray-4" />
              </Link>
            </li>
          ))}
        </ul>

        <Button
          className="mt-6"
          variant="solid"
          onClick={() => navigate({ to: '/deals/view' })}
        >
          Go to the app
        </Button>
      </div>
    </div>
  )
}

/** `/not-permitted` — the guard sends people here rather than to a blank screen. */
export function NotPermittedPage() {
  return (
    <Centered
      title="Not permitted"
      body="You do not have access to that record. If you think you should, ask whoever administers this workspace."
    />
  )
}

/** The catch-all. TanStack Router renders it for any path the tree does not match. */
export function InvalidPage() {
  return <Centered title="Page not found" body="That URL does not lead anywhere in this app." />
}

function Centered({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
      <h1 className="text-xl font-semibold text-ink-gray-9">{title}</h1>
      <p className="max-w-md text-base text-ink-gray-5">{body}</p>
      <Button className="mt-3" variant="subtle" asChild>
        <Link to="/deals/view">Back to deals</Link>
      </Button>
    </div>
  )
}
