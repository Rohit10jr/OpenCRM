import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { call, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'
import { ErrorMessage, FormControl } from '@/components/ui/input'
import { AuthLayout } from './AuthLayout'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [sent, setSent] = useState(false)
  const [loading, setLoading] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const result = await call<string>(
        'frappe.core.doctype.user.user.reset_password',
        { user: email },
      )
      // Whatever came back, show it. The server sends one sentence for every outcome —
      // including "no such user", which is a 200 with the same body as success.
      setMessage(result || 'Please check your inbox.')
      setSent(true)
    } catch (e) {
      // Reaching here means the request itself failed — a network error, or the rate
      // limit. Not "no such user".
      setError(errorMessage(e, 'Could not send the reset email. Please try again shortly.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle={sent ? '' : 'We will email you a link.'}
      footer={
        <Link className="hover:text-ink-gray-7" to="/login">
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        <p className="text-base text-ink-gray-7">{message}</p>
      ) : (
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <FormControl
            label="Email or username"
            type="text"
            inputMode="email"
            name="username"
            autoComplete="username"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <ErrorMessage message={error} />
          <Button className="w-full" variant="solid" type="submit" loading={loading}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthLayout>
  )
}
