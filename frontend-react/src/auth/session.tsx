import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { call } from '@/api/client'
import { clearTokens, getTokenUser, setTokens, type TokenPair } from './tokens'

/**
 * Who is signed in. The React answer to `stores/session.js`.
 *
 * A Pinia store in the Vue app; here it is context, because that is what React
 * developers reach for and there is exactly one value in it. No state library.
 *
 * **This is for rendering, not for routing.** The route guard reads token storage
 * directly (`isAuthenticated`), because React state updates on the next render and a
 * navigation in the same tick as signing in would run the guard on the pre-login value.
 * That is the bug phase 8 shipped in Vue and it reappeared here until the guard moved.
 *
 * Pages that receive a token pair still call `acceptTokens` rather than `setTokens`, so
 * the chrome updates too.
 */

type Session = {
  user: string | null
  isLoggedIn: boolean
  acceptTokens: (tokens: TokenPair) => boolean
  login: (usr: string, pwd: string) => Promise<void>
  logout: () => Promise<void>
}

const SessionContext = createContext<Session | null>(null)

function currentUser(): string | null {
  const user = getTokenUser()
  return user === 'Guest' ? null : user
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<string | null>(currentUser)

  const acceptTokens = useCallback((tokens: TokenPair) => {
    setTokens(tokens)
    const next = currentUser()
    setUser(next)
    return Boolean(next)
  }, [])

  const login = useCallback(
    async (usr: string, pwd: string) => {
      // JWT PATCH: `/api/method/login` returns a token pair instead of setting `sid`.
      const tokens = await call<TokenPair>('login', { usr, pwd })
      acceptTokens(tokens)
    },
    [acceptTokens],
  )

  const logout = useCallback(async () => {
    try {
      await call('logout')
    } finally {
      // JWT PATCH: nothing to expire server-side, so drop the tokens locally — and do it
      // even if the call failed, or a server hiccup would leave the user stuck signed in.
      clearTokens()
      setUser(null)
    }
  }, [])

  const value = useMemo<Session>(
    () => ({ user, isLoggedIn: Boolean(user), acceptTokens, login, logout }),
    [user, acceptTokens, login, logout],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error('useSession must be used inside <SessionProvider>')
  return session
}
