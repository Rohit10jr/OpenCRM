import { Link } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'

/**
 * The two dead-end screens.
 *
 * Their own file rather than living beside `Welcome`, because one of them is the router's
 * `defaultNotFoundComponent` and must be in the entry chunk, while `Welcome` is lazy.
 * Vite warns when a module is both statically and dynamically imported and quietly gives up
 * on splitting it — which would have pulled Welcome back into the entry chunk.
 */

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
