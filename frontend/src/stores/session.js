import { defineStore } from 'pinia'
import { createResource } from 'frappe-ui'
import router from '@/router'
import { ref, computed } from 'vue'
import { clearTokens, getTokenUser, setTokens } from '@/auth/tokens'

export const sessionStore = defineStore('crm-session', () => {
  // JWT PATCH (see ../../JWT_PATCH.md): the port issues bearer tokens instead of the
  // `sid`/`user_id` cookie pair, so the current user comes out of the access token.
  function sessionUser() {
    let _sessionUser = getTokenUser()
    if (_sessionUser === 'Guest') {
      _sessionUser = null
    }
    return _sessionUser
  }

  let user = ref(sessionUser())
  const isLoggedIn = computed(() => !!user.value)

  /**
   * Take a token pair and become signed in.
   *
   * **`setTokens` alone is not enough**, and that is the whole reason this exists.
   * `isLoggedIn` is computed from `user`, a ref read once at store creation — so a page
   * that writes tokens to localStorage and then routes is still `isLoggedIn === false` to
   * the navigation guard, which bounces it straight back to Login.
   *
   * Found by the phase-8 review: `UpdatePassword.vue` and `AcceptInvitation.vue` both did
   * exactly that, so setting a password succeeded on the server and returned the user to
   * the login page. Every backend test passed, and the end-to-end walk passed, because
   * neither runs a browser.
   *
   * Any future page that receives tokens should call this rather than `setTokens`.
   */
  function acceptTokens(data) {
    setTokens(data || {})
    user.value = sessionUser()
    return isLoggedIn.value
  }

  const login = createResource({
    url: 'login',
    onError() {
      throw new Error(__('Invalid Email or Password'))
    },
    // JWT PATCH: /api/method/login now returns a token pair instead of setting `sid`.
    //
    // The pair sits under `message`, and it arrives wrapped: frappe-ui's request layer
    // returns the *whole* body for the login URL (frappeRequest.ts, `url ===
    // '/api/method/login'`), because upstream's login answer keeps `home_page` and
    // `full_name` at the top level. Every other endpoint is unwrapped to `message`
    // before a resource sees it, which is how UpdatePassword.vue and AcceptInvitation.vue
    // receive a bare pair. Reading `data` here stored nothing and the guard bounced the
    // user straight back to Login (docs/FINDINGS.md 32).
    onSuccess(data) {
      acceptTokens(data?.message ?? data)
      login.reset()
      // Phase 8: return them to whatever they were trying to reach. The guard puts it in
      // `?redirect=` when it bounces an unauthenticated visitor.
      //
      // Only a path, never a full URL: `redirect` comes from the query string, so a caller
      // can put anything there. Accepting `https://elsewhere.example/` would make the
      // login page an open redirect — a phishing link that really does log you in and then
      // lands you somewhere else.
      const target = router.currentRoute.value.query.redirect
      const safe = typeof target === 'string' && /^\/(?!\/)/.test(target) ? target : '/'
      router.replace({ path: safe })
    },
  })

  const logout = createResource({
    url: 'logout',
    onSuccess() {
      // JWT PATCH: nothing to expire server-side, so drop the tokens locally.
      clearTokens()
      user.value = null
      // Phase 8: the second half of the same bug the router had. This was
      // `window.location.href = '/login?redirect-to=/crm'`, which took a user who had just
      // signed out to a URL nothing serves. Caught by the phase-8 review, outside the
      // files it was asked to look at.
      router.replace({ name: 'Login' })
    },
  })

  return {
    user,
    isLoggedIn,
    acceptTokens,
    login,
    logout,
  }
})
