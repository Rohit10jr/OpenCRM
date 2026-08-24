import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { call } from '@/api/client'
import { clearTokens, getTokenUser, setTokens, type TokenPair } from './tokens'

/**
 * Who is signed in. The React answer to `stores/session.js`.
 *
 * A Pinia store in the Vue app; here it is context, because that is what React
 * developers reach for and there is exactly one value in it. No state library.
 *
 * **The reason this is state and not a call to `getTokenUser()` at each read** is a bug
 * phase 8 shipped: `UpdatePassword.vue` and `AcceptInvitation.vue` wrote tokens to
 * localStorage and then navigated, and the route guard — reading a value captured
 * earlier — still saw a logged-out user and bounced them back to Login. Setting a
 * password succeeded on the server and returned the user to the login page. Every
 * backend test passed, and the end-to-end walk passed, because neither runs a browser.
 *
 * So: any page that receives a token pair calls `acceptTokens`, never `setTokens`.
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
