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

  const login = createResource({
    url: 'login',
    onError() {
      throw new Error(__('Invalid Email or Password'))
    },
    // JWT PATCH: /api/method/login now returns a token pair instead of setting `sid`.
    onSuccess(data) {
      setTokens(data || {})
      user.value = sessionUser()
      login.reset()
      router.replace({ path: '/' })
    },
  })

  const logout = createResource({
    url: 'logout',
    onSuccess() {
      // JWT PATCH: nothing to expire server-side, so drop the tokens locally.
      clearTokens()
      user.value = null
      window.location.href = '/login?redirect-to=/crm'
    },
  })

  return {
    user,
    isLoggedIn,
    login,
    logout,
  }
})
