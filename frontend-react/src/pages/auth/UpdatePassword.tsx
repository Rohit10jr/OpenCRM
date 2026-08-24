import { useState } from 'react'
import axios from 'axios'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { call, errorMessage } from '@/api/client'
import { useSession } from '@/auth/session'
import type { TokenPair } from '@/auth/tokens'
import { Button } from '@/components/ui/button'
import { ErrorMessage, FormControl } from '@/components/ui/input'
import { AuthLayout } from './AuthLayout'

export function UpdatePasswordPage() {
  const { key } = useSearch({ from: '/public/update-password' })
  const { acceptTokens } = useSession()
  const navigate = useNavigate()

  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [linkDead, setLinkDead] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError('')

    // Checked here because it is a *typing* mistake, not a policy: the server has no
    // second field to compare against, and a round trip to be told you mistyped is a poor
    // trade. The actual password rules are enforced server-side, where a client that does
    // not run this file cannot skip them.
    if (newPassword !== confirmPassword) {
      setError('The two passwords do not match')
      return
    }

    setLoading(true)
    try {
      const result = await call<TokenPair>(
        'frappe.core.doctype.user.user.update_password',
        {
          new_password: newPassword,
          ...(key ? { key } : { old_password: oldPassword }),
        },
      )

      // 200 carries the same payload `login` returns, so this is a real sign-in.
      //
      // `acceptTokens`, not `setTokens`: the guard reads session state, and writing
      // tokens to localStorage alone does not update it — navigating afterwards bounced
      // straight back to Login. Found by the phase-8 review.
      acceptTokens(result)
      navigate({ to: '/deals/view' })
    } catch (e) {
      if (axios.isAxiosError(e) && e.response?.status === 410) {
        // Nothing on this page can fix a dead link.
        setLinkDead(true)
      }
      setError(errorMessage(e, 'Could not set your password'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title={key ? 'Choose a password' : 'Change your password'}
      subtitle={linkDead ? '' : 'At least 8 characters, and not one you use elsewhere.'}
    >
      {linkDead ? (
        <div className="flex flex-col gap-4">
          <ErrorMessage message={error} />
          <Button variant="solid" onClick={() => navigate({ to: '/forgot-password' })}>
            Request a new link
          </Button>
        </div>
      ) : (
        <form className="flex flex-col gap-4" onSubmit={submit}>
          {!key ? (
            <FormControl
              label="Current password"
              type="password"
              autoComplete="current-password"
              required
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
            />
          ) : null}
          <FormControl
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            autoFocus
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <FormControl
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            required
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
          <ErrorMessage message={error} />
          <Button className="w-full" variant="solid" type="submit" loading={loading}>
            Set password
          </Button>
        </form>
      )}
    </AuthLayout>
  )
}
