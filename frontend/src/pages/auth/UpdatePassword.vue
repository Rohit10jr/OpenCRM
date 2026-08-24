<!--
  Set / reset password. The page the emailed link lands on.

  Upstream's equivalent is `frappe/www/update-password.html`, a Jinja page that branches on
  the endpoint's status code. The markup does not port; the branching does, and it is the
  part that matters:

    200 — done, and the response carries a token pair, so we are logged in
    401 — the current password was wrong
    410 — the link is expired, used, or invalid

  410 is the one that needs a real screen rather than an inline error: there is nothing to
  retry on this page, and the only useful next step is asking for another link.
-->
<template>
  <AuthLayout :title="title" :subtitle="subtitle">
    <div v-if="linkDead" class="text-center">
      <p class="text-ink-gray-7 text-p-base">{{ error }}</p>
      <Button
        class="mt-5 w-full"
        variant="solid"
        :label="__('Request a new link')"
        @click="$router.push({ name: 'Forgot Password' })"
      />
    </div>

    <form v-else class="flex flex-col gap-4" @submit.prevent="submit">
      <FormControl
        v-if="!key"
        v-model="oldPassword"
        type="password"
        :label="__('Current password')"
        autocomplete="current-password"
        required
      />
      <FormControl
        v-model="newPassword"
        type="password"
        :label="__('New password')"
        autocomplete="new-password"
        required
        autofocus
      />
      <FormControl
        v-model="confirmPassword"
        type="password"
        :label="__('Confirm new password')"
        autocomplete="new-password"
        required
      />

      <ErrorMessage v-if="error" :message="error" />

      <Button
        class="w-full"
        variant="solid"
        :label="__('Set password')"
        :loading="loading"
        type="submit"
      />
    </form>
  </AuthLayout>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, ErrorMessage, FormControl } from 'frappe-ui'
import { jwtRequest } from '@/auth/jwtRequest'
import { setTokens } from '@/auth/tokens'
import AuthLayout from './AuthLayout.vue'

const route = useRoute()
const router = useRouter()

const key = computed(() => route.query.key || '')
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const loading = ref(false)
const linkDead = ref(false)

const title = computed(() =>
  key.value ? __('Choose a password') : __('Change your password'),
)
const subtitle = computed(() =>
  linkDead.value ? '' : __('At least 8 characters, and not one you use elsewhere.'),
)

async function submit() {
  error.value = ''

  // Checked here because it is a *typing* mistake, not a policy: the server has no second
  // field to compare against, and a round trip to be told you mistyped is a poor trade.
  // The actual password rules are enforced server-side, where a client that does not run
  // this file cannot skip them.
  if (newPassword.value !== confirmPassword.value) {
    error.value = __('The two passwords do not match')
    return
  }

  loading.value = true
  try {
    const result = await jwtRequest({
      url: '/api/method/frappe.core.doctype.user.user.update_password',
      method: 'POST',
      params: {
        new_password: newPassword.value,
        ...(key.value ? { key: key.value } : { old_password: oldPassword.value }),
      },
    })

    // 200 carries the same payload `login` returns, so this is a real sign-in.
    setTokens(result || {})
    router.replace({ path: '/' })
  } catch (e) {
    const status = e?.response?.status || e?.status
    if (status === 410) {
      // Nothing on this page can fix a dead link.
      linkDead.value = true
    }
    error.value = e.message || __('Could not set your password')
  } finally {
    loading.value = false
  }
}
</script>
