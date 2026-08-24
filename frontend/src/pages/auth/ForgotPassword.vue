<!--
  Forgot password.

  **The screen shows the same thing whatever happened**, because the server does. A page
  that said "no such account" would undo the server's whole reason for having one response
  (CWE-204, username enumeration) — the enumeration would just move to the browser.
-->
<template>
  <AuthLayout
    :title="__('Reset your password')"
    :subtitle="sent ? '' : __('We will email you a link to choose a new one.')"
  >
    <div v-if="sent" class="text-center">
      <p class="text-ink-gray-7 text-p-base">{{ message }}</p>
      <Button
        class="mt-5 w-full"
        variant="subtle"
        :label="__('Back to sign in')"
        @click="$router.push({ name: 'Login' })"
      />
    </div>

    <form v-else class="flex flex-col gap-4" @submit.prevent="submit">
      <FormControl
        v-model="email"
        type="email"
        :label="__('Email')"
        name="email"
        autocomplete="username"
        required
        autofocus
      />

      <ErrorMessage v-if="error" :message="error" />

      <Button
        class="w-full"
        variant="solid"
        :label="__('Send reset link')"
        :loading="loading"
        type="submit"
      />
    </form>

    <template #footer>
      <router-link class="hover:text-ink-gray-7" :to="{ name: 'Login' }">
        {{ __('Back to sign in') }}
      </router-link>
    </template>
  </AuthLayout>
</template>

<script setup>
import { ref } from 'vue'
import { Button, ErrorMessage, FormControl } from 'frappe-ui'
import { jwtRequest } from '@/auth/jwtRequest'
import AuthLayout from './AuthLayout.vue'

const email = ref('')
const error = ref('')
const message = ref('')
const sent = ref(false)
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    const result = await jwtRequest({
      url: '/api/method/frappe.core.doctype.user.user.reset_password',
      method: 'POST',
      params: { user: email.value },
    })
    // Whatever came back, show it. The server sends one sentence for every outcome.
    message.value = result?.message || __('Please check your inbox.')
    sent.value = true
  } catch (e) {
    // Reaching here means the request itself failed — a network error, or the rate limit.
    // Not "no such user": that is a 200 with the same body as success.
    error.value =
      e.message || __('Could not send the reset email. Please try again shortly.')
  } finally {
    loading.value = false
  }
}
</script>
