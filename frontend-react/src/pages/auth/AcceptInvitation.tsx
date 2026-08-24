import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Loader2 } from 'lucide-react'
import { call, errorMessage } from '@/api/client'
import { useSession } from '@/auth/session'
import type { TokenPair } from '@/auth/tokens'
import { ErrorMessage } from '@/components/ui/input'
import { AuthLayout } from './AuthLayout'

type AcceptResult = TokenPair & { status?: string; redirect_to?: string }

export function AcceptInvitationPage() {
  const { key } = useSearch({ from: '/public/accept-invitation' })
  const { acceptTokens } = useSession()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // The invitation key is single-use, so this must fire exactly once. React 18's
  // StrictMode double-invokes effects in development, which would burn the key on the
  // first render and show "invalid or expired" on the second.
  const claimed = useRef(false)

  useEffect(() => {
    if (claimed.current) return
    claimed.current = true

    if (!key) {
      setError('Invalid or expired key')
      setLoading(false)
      return
    }

    call<AcceptResult>('crm.api.accept_invitation', { key })
      .then((result) => {
        if (result?.status === 'set_password') {
          // `redirect_to` is an absolute URL built server-side, and its `key` is a
          // one-hour reset key rather than the invitation key — two clocks, deliberately.
          // Take the query off it and route internally rather than reloading the SPA.
          const resetKey = new URL(result.redirect_to as string).searchParams.get('key')
          navigate({ to: '/update-password', search: { key: resetKey ?? '' } })
          return
        }

        // An address that already had an account: the response is a token pair.
        acceptTokens(result)
        navigate({ to: '/deals/view' })
      })
      .catch((e) => {
        // One message for every failure — used, unknown, expired. The endpoint answers
        // the same way for all three, and repeating that here keeps the key unprobeable.
        setError(errorMessage(e, 'Invalid or expired key'))
      })
      .finally(() => setLoading(false))
  }, [key, acceptTokens, navigate])

  return (
    <AuthLayout title="Accepting your invitation" subtitle={loading ? 'One moment…' : ''}>
      {loading ? (
        <div className="flex justify-center py-4">
          <Loader2 className="h-5 w-5 animate-spin text-ink-gray-5" />
        </div>
      ) : (
        <ErrorMessage message={error} />
      )}
    </AuthLayout>
  )
}
