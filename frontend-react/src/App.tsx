import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { Toaster } from 'sonner'
import { SessionProvider } from '@/auth/session'
import { TooltipProvider } from '@/components/ui/primitives'
import { SocketProvider } from '@/realtime/useSocket'
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

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <SocketProvider>
        <TooltipProvider delayDuration={300}>
          {/* The router's auth guard reads token storage directly (`isAuthenticated`),
              so it needs nothing from React here. */}
          <RouterProvider router={router} />
          <Toaster position="bottom-right" />
        </TooltipProvider>
        </SocketProvider>
      </SessionProvider>
    </QueryClientProvider>
  )
}
