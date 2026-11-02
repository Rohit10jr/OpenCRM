<template>
  <Dialog v-model:open="show" :size="'sm'">
    <template #body>
      <div class="p-4 pt-5">
        <div class="flex justify-center">
          <div class="flex flex-col items-center">
            <CRMLogo class="mb-3 size-12" />
            <!-- Upstream: Frappe CRM (renamed to Open CRM, KNOWN_ISSUES.md 12) -->
            <h3 class="text-2xl-semibold text-ink-gray-9">Open CRM</h3>
          </div>
        </div>
        <hr class="border-t my-3 mx-2" />
        <div>
          <a
            v-for="link in links"
            :key="link.label"
            class="flex py-2 px-2 hover:bg-surface-gray-1 rounded cursor-pointer"
            target="_blank"
            :href="link.url"
          >
            <component
              :is="link.icon"
              v-if="link.icon"
              class="size-4 mr-2 text-ink-gray-7"
            />
            <span class="text-base text-ink-gray-8">
              {{ link.label }}
            </span>
          </a>
        </div>
        <!-- Upstream's footer, restored 31 Oct 2026: the interface is Frappe CRM's under
          AGPL-3.0 (LICENSE), whose notice belongs where the program shows its legal notices. -->
        <hr class="border-t my-3 mx-2" />
        <p class="text-sm text-ink-gray-6 px-2 mt-2">
          © Frappe Technologies Pvt. Ltd. and contributors
        </p>
        <!-- Port only: the port's own notice. -->
        <p class="text-sm text-ink-gray-6 px-2 mt-1">
          Open CRM port © 2026 Rohit10jr and contributors
        </p>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
import CRMLogo from '@/components/Icons/CRMLogo.vue'
import LucideGlobe from '~icons/lucide/globe'
// lucide-static 1.x has no brand icons, so no `github`; `code` stands in.
import LucideCode from '~icons/lucide/code'
import LucideBug from '~icons/lucide/bug'

let show = defineModel({ type: Boolean })

// Port only: upstream's links describe Frappe CRM's website, docs and support rather
// than this deployment (kept in a comment below). These point at the port's source,
// which AGPL-3.0 section 13 asks a network service to offer its users, its issue
// tracker, and the project it is based on.
const repoLink = 'https://github.com/Rohit10jr/OpenCRM'

let links = [
  {
    label: __('Source Code'),
    url: repoLink,
    icon: LucideCode,
  },
  {
    label: __('Report an Issue'),
    url: `${repoLink}/issues`,
    icon: LucideBug,
  },
  {
    label: __('Based on Frappe CRM'),
    url: 'https://github.com/frappe/crm',
    icon: LucideGlobe,
  },
]

/* Upstream's links:
import LucideGlobe from '~icons/lucide/globe'
import LucideGitHub from '~icons/lucide/github'
import LucideHeadset from '~icons/lucide/headset'
import LucideBug from '~icons/lucide/bug'
import LucideBookOpen from '~icons/lucide/book-open'

let upstreamLinks = [
  {
    label: __('Website'),
    url: 'https://frappe.io/crm',
    icon: LucideGlobe,
  },
  {
    label: __('GitHub Repository'),
    url: 'https://github.com/frappe/crm',
    icon: LucideGitHub,
  },
  {
    label: __('Documentation'),
    url: 'https://docs.frappe.io/crm',
    icon: LucideBookOpen,
  },
  {
    label: __('Report an Issue'),
    url: 'https://github.com/frappe/crm/issues',
    icon: LucideBug,
  },
  {
    label: __('Contact Support'),
    url: 'https://support.frappe.io',
    icon: LucideHeadset,
  },
]
*/
</script>
