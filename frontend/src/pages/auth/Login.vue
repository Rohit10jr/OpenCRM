<!--
  Login. The backend for this shipped in phase 0 — `POST /api/method/login` issues the
  token pair and `stores/session.js` already stores it. This is the page that was missing.
-->
<template>
  <AuthLayout :title="__('Sign in to Frappe CRM')">
    <form class="flex flex-col gap-4" @submit.prevent="submit">
      <FormControl
        v-model="email"
        type="email"
        :label="__('Email')"
        name="email"
        autocomplete="username"
        required
        autofocus
      />
      <FormControl
        v-model="password"
        type="password"
        :label="__('Password')"
        name="password"
        autocomplete="current-password"
        required
      />

      <ErrorMessage v-if="error" :message="error" />

      <Button
        class="w-full"
        variant="solid"
        :label="__('Sign in')"
        :loading="loading"
        type="submit"
      />
    </form>

    <template #footer>
      <router-link class="hover:text-ink-gray-7" :to="{ name: 'Forgot Password' }">
        {{ __('Forgot your password?') }}
      </router-link>
    </template>
  </AuthLayout>
</template>

<script setup>
import { ref } from 'vue'
import { Button, ErrorMessage, FormControl } from 'frappe-ui'
import AuthLayout from './AuthLayout.vue'
import { sessionStore } from '@/stores/session'

const { login } = sessionStore()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    // `session.js`'s `login` resource stores the tokens and routes to '/' on success, so
    // there is nothing to do here on the happy path.
    await login.submit({ usr: email.value, pwd: password.value })
  } catch (e) {
    // The store's onError throws a generic message deliberately: the server does not say
    // whether it was the address or the password that was wrong, and neither should this.
    error.value = e.message || __('Invalid Email or Password')
  } finally {
    loading.value = false
  }
}
</script>
