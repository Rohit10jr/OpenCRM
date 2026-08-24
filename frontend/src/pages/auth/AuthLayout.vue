<!--
  The shell the four auth screens share.

  PHASE_8_AUTH_AND_DESK.md: these pages live **inside the Vue app**. `router.js` used to
  send an unauthenticated visitor to `window.location.href = '/login?redirect-to=/crm'`,
  which leaves the SPA for a URL nothing serves — `config/urls.py` has only `admin/` and
  `api/`. That redirect was the bug, not the contract.

  Deliberately not the app chrome: no sidebar, no user dropdown, nothing that reads a
  session. These render for someone who has no account yet.
-->
<template>
  <div
    class="flex flex-col items-center justify-center min-h-screen bg-surface-gray-1 px-4"
  >
    <div class="w-full max-w-sm">
      <div class="text-center mb-6">
        <h1 class="text-ink-gray-9 text-2xl-semibold">{{ title }}</h1>
        <p v-if="subtitle" class="text-ink-gray-5 text-p-base mt-2">
          {{ subtitle }}
        </p>
      </div>

      <div class="bg-surface-white rounded-lg border p-6 shadow-sm">
        <slot />
      </div>

      <div v-if="$slots.footer" class="text-center mt-4 text-p-sm text-ink-gray-5">
        <slot name="footer" />
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
})
</script>
