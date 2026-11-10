<template>
  <div class="contents">
    <DataImport
      :doctype="route.params.doctype"
      :importName="route.params.importName"
      :doctypeMap="doctypeMap"
      :socket="$socket"
    />
  </div>
</template>

<script setup>
import { usePageMeta } from 'frappe-ui'
import { DataImport } from '@framework/ui/components/DataImport'
import { globalStore } from '@/stores/global'
import { useRoute } from 'vue-router'

const route = useRoute()
const { $socket } = globalStore()

const doctypeMap = {
  'CRM Lead': {
    title: 'Leads',
    listRoute: '/crm/leads',
    pageRoute: `/crm/leads/docname`,
  },
  'CRM Deal': {
    title: 'Deals',
    listRoute: '/crm/deals',
    pageRoute: `/crm/deals/docname`,
  },
  Contact: {
    title: 'Contacts',
    listRoute: '/crm/contacts',
    pageRoute: `/crm/contacts/docname`,
  },
  'CRM Task': {
    title: 'Tasks',
    listRoute: '/crm/tasks',
  },
  'CRM Organization': {
    title: 'Organizations',
    listRoute: '/crm/organizations',
    pageRoute: `/crm/organizations/docname`,
  },
  'CRM Call Log': {
    title: 'Call Log',
    listRoute: '/crm/call-logs',
  },
}

usePageMeta(() => {
  return {
    title: __('Data Import'),
  }
})
</script>

<style scoped>
/* Port only: Data Import accepts CSV uploads only; keep the shared framework screens unchanged. */
:deep(div.leading-5 > span.cursor-pointer + span.cursor-pointer) {
  display: none;
}

:deep(div:has(> div > input[placeholder='Add Google Sheets Link'])) {
  display: none;
}
</style>
