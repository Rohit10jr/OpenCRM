import { useMemo } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { Toaster } from 'sonner'
import { SessionProvider, useSession } from '@/auth/session'
import { TooltipProvider } from '@/components/ui/primitives'
import { router } from '@/router'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The Vue app's `createResource` did not retry, and a retried 403 just delays the
      // error the user needs to see. The 401 path is the interceptor's job, not this one's.
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
})

/**
 * The router needs `isLoggedIn` in its context but the session lives in React, so the
 * guard reads it through a function rather than a snapshot — otherwise a navigation
 * immediately after signing in would still see the old value.
 */
function Routes() {
  const session = useSession()
  const context = useMemo(
    () => ({ isLoggedIn: () => session.isLoggedIn }),
    [session.isLoggedIn],
  )
  return <RouterProvider router={router} context={context} />
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <TooltipProvider delayDuration={300}>
          <Routes />
          <Toaster position="bottom-right" />
        </TooltipProvider>
      </SessionProvider>
    </QueryClientProvider>
  )
}
