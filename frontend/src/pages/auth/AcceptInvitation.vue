<!--
  Invitation acceptance.

  The endpoint does the work; this page exists because the *link in the email* has to land
  somewhere, and upstream's landing place is a Desk URL this port does not serve.

  Two outcomes, both from the endpoint:
    set_password — a brand-new account, handed a one-hour reset key. Go and choose one.
    logged_in    — the address already had an account. Tokens are in the response.
-->
<template>
  <AuthLayout :title="__('Joining Frappe CRM')" :subtitle="subtitle">
    <div class="text-center">
      <Spinner v-if="loading" class="w-6 h-6 mx-auto text-ink-gray-5" />

      <template v-else-if="error">
        <p class="text-ink-gray-7 text-p-base">{{ error }}</p>
        <Button
          class="mt-5 w-full"
          variant="subtle"
          :label="__('Go to sign in')"
          @click="$router.push({ name: 'Login' })"
        />
      </template>
    </div>
  </AuthLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, Spinner } from 'frappe-ui'
import { jwtRequest } from '@/auth/jwtRequest'
import { setTokens } from '@/auth/tokens'
import AuthLayout from './AuthLayout.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const error = ref('')

const subtitle = computed(() =>
  loading.value ? __('One moment…') : '',
)

onMounted(async () => {
  const key = route.query.key || ''
  if (!key) {
    error.value = __('Invalid or expired key')
    loading.value = false
    return
  }

  try {
    const result = await jwtRequest({
      url: '/api/method/crm.api.accept_invitation',
      method: 'POST',
      params: { key },
    })

    if (result?.status === 'set_password') {
      // `redirect_to` is an absolute URL built server-side, and its `key` is a one-hour
      // reset key rather than the invitation key — two clocks, deliberately. Take the
      // query off it and route internally rather than reloading the SPA.
      const resetKey = new URL(result.redirect_to).searchParams.get('key')
      router.replace({ name: 'Update Password', query: { key: resetKey } })
      return
    }

    // An address that already had an account: the response is a token pair.
    setTokens(result || {})
    router.replace({ path: '/' })
  } catch (e) {
    // One message for every failure — used, unknown, expired. The endpoint answers the
    // same way for all three, and repeating that here keeps the key unprobeable.
    error.value = e.message || __('Invalid or expired key')
  } finally {
    loading.value = false
  }
})
</script>
