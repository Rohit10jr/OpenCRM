<template>
  <Dialog v-model:open="show" :size="'sm'">
    <template #body>
      <div class="p-4 pt-5">
        <div class="flex justify-center">
          <div class="flex flex-col items-center">
            <CRMLogo class="mb-3 size-12" />
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
        <hr class="border-t my-3 mx-2" />
        <p class="text-base text-ink-gray-7 px-2">
          {{ __('A CRM for managing leads, deals, contacts and organizations, with tasks, notes, calls and email in one place.') }}
        </p>
        <hr class="border-t my-3 mx-2" />
        <!--
          The copyright notice stays: the interface is Frappe CRM's, under AGPL-3.0,
          whose notices must be kept and shown where the program shows its legal notices.
        -->
        <p class="text-sm text-ink-gray-6 px-2 mt-2">
          {{ __('Based on Frappe CRM.') }} © Frappe Technologies Pvt. Ltd. and contributors.
          {{ __('Licensed under the GNU AGPL v3.') }}
        </p>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
import CRMLogo from '@/components/Icons/CRMLogo.vue'
import LucideGlobe from '~icons/lucide/globe'
import LucideLayoutDashboard from '~icons/lucide/layout-dashboard'
import LucideBookOpen from '~icons/lucide/book-open'

let show = defineModel({ type: Boolean })

// Links into the app itself, like the help centre's (AppSidebar.vue, `helpLink`):
// upstream's pointed at frappe.io, its GitHub repository, docs and support, which
// describe Frappe CRM rather than this deployment. Kept in a comment below.
const appLink = `${window.location.origin}/crm`

let links = [
  {
    label: __('Home'),
    url: appLink,
    icon: LucideGlobe,
  },
  {
    label: __('Dashboard'),
    url: `${appLink}/dashboard`,
    icon: LucideLayoutDashboard,
  },
  {
    label: __('Leads'),
    url: `${appLink}/leads/view/list`,
    icon: LucideBookOpen,
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
