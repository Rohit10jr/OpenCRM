import { useState } from 'react'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { ErrorMessage, FormControl } from '@/components/ui/input'
import { useSession } from '@/auth/session'
import { AuthLayout } from './AuthLayout'

export function LoginPage() {
  const { login } = useSession()
  const navigate = useNavigate()
  const { redirect } = useSearch({ from: '/public/login' })

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      // The route's `validateSearch` has already rejected anything that is not a
      // same-site path, so this cannot be an open redirect.
      navigate({ to: redirect ?? '/deals/view' })
    } catch {
      // Deliberately generic: the server does not say whether it was the address or the
      // password that was wrong, and neither should this.
      setError('Invalid Email or Password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Sign in to Frappe CRM"
      footer={
        <Link className="hover:text-ink-gray-7" to="/forgot-password">
          Forgot your password?
        </Link>
      }
    >
      <form className="flex flex-col gap-4" onSubmit={submit}>
        {/*
          `type="text"`, not `type="email"`. The backend authenticates against `User.name`,
          and the seeded superuser's name is literally `Administrator` — not an address.
          With `type="email"` the browser refuses to submit it, so the one account that
          always exists could not log in. Found by the phase-8 review.
        */}
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
        <FormControl
          label="Password"
          type="password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <ErrorMessage message={error} />

        <Button className="w-full" variant="solid" type="submit" loading={loading}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  )
}
