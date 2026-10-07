import { createRouter, createWebHistory } from 'vue-router'
import { call } from 'frappe-ui'
import { usersStore } from '@/stores/users'
import { sessionStore } from '@/stores/session'
import { viewsStore } from '@/stores/views'

let personaChecked = false
export const PERSONA_DONE_KEY = 'crm_persona_captured'

async function shouldCapturePersona() {
  // Client-side flag guards against re-prompting if the server persist failed.
  if (localStorage.getItem(PERSONA_DONE_KEY)) return false
  const captured = await call('frappe.client.get_single_value', {
    doctype: 'FCRM Settings',
    field: 'persona_captured',
  })
  if (captured) return false
  // The wizard only feeds telemetry; skip it entirely if the user opted out.
  const { enabled } =
    (await call('frappe.utils.telemetry.pulse.client.boot_config')) || {}
  return !!enabled
}

const routes = [
  {
    path: '/',
    name: 'Home',
  },
  // Phase 8. The auth screens, inside the app.
  //
  // `isPublic` is what the navigation guard below reads: without it, the guard's
  // "not logged in" branch would send an unauthenticated visitor to Login from Login.
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/pages/auth/Login.vue'),
    meta: { isPublic: true },
  },
  {
    path: '/forgot-password',
    name: 'Forgot Password',
    component: () => import('@/pages/auth/ForgotPassword.vue'),
    meta: { isPublic: true },
  },
  {
    // The URL the reset email links to. `frappe_core/password_reset.py:reset_link` builds
    // it, so the two must agree — a mismatch is a link that 404s, and nothing fails
    // until somebody clicks one.
    path: '/update-password',
    name: 'Update Password',
    component: () => import('@/pages/auth/UpdatePassword.vue'),
    meta: { isPublic: true },
  },
  {
    path: '/accept-invitation',
    name: 'Accept Invitation',
    component: () => import('@/pages/auth/AcceptInvitation.vue'),
    meta: { isPublic: true },
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/pages/MobileNotification.vue'),
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/pages/Dashboard.vue'),
  },
  {
    alias: '/leads',
    path: '/leads/view/:viewType?',
    name: 'Leads',
    component: () => import('@/pages/Leads.vue'),
  },
  {
    path: '/leads/:leadId',
    name: 'Lead',
    component: () => import(`@/pages/${handleMobileView('Lead')}.vue`),
    props: true,
  },
  {
    alias: '/deals',
    path: '/deals/view/:viewType?',
    name: 'Deals',
    component: () => import('@/pages/Deals.vue'),
  },
  {
    path: '/deals/:dealId',
    name: 'Deal',
    component: () => import(`@/pages/${handleMobileView('Deal')}.vue`),
    props: true,
  },
  {
    alias: '/notes',
    path: '/notes/view/:viewType?',
    name: 'Notes',
    component: () => import('@/pages/Notes.vue'),
  },
  {
    alias: '/tasks',
    path: '/tasks/view/:viewType?',
    name: 'Tasks',
    component: () => import('@/pages/Tasks.vue'),
  },
  {
    alias: '/contacts',
    path: '/contacts/view/:viewType?',
    name: 'Contacts',
    component: () => import('@/pages/Contacts.vue'),
  },
  {
    path: '/contacts/:contactId',
    name: 'Contact',
    component: () => import(`@/pages/${handleMobileView('Contact')}.vue`),
    props: true,
  },
  {
    alias: '/organizations',
    path: '/organizations/view/:viewType?',
    name: 'Organizations',
    component: () => import('@/pages/Organizations.vue'),
  },
  {
    path: '/organizations/:organizationId',
    name: 'Organization',
    component: () => import(`@/pages/${handleMobileView('Organization')}.vue`),
    props: true,
  },
  {
    alias: '/call-logs',
    path: '/call-logs/view/:viewType?',
    name: 'Call Logs',
    component: () => import('@/pages/CallLogs.vue'),
  },
  {
    path: '/data-import',
    name: 'DataImportList',
    component: () => import('@/pages/DataImport.vue'),
  },
  {
    path: '/data-import/doctype/:doctype',
    name: 'NewDataImport',
    component: () => import('@/pages/DataImport.vue'),
    props: true,
  },
  {
    path: '/data-import/:importName',
    name: 'DataImport',
    component: () => import('@/pages/DataImport.vue'),
    props: true,
  },
  {
    path: '/welcome',
    name: 'Welcome',
    component: () => import('@/pages/Welcome.vue'),
  },
  {
    path: '/onboarding',
    name: 'Onboarding',
    component: () => import('@/pages/PersonaForm.vue'),
  },
  {
    // Port patch (docs/FINDINGS.md 83, upstream bug 48): upstream's `/:invalidpath`
    // matches one segment, so `/crm/leadsdss/CRM-LEAD-...` matched nothing and drew a
    // blank page. `(.*)*` is Vue Router's catch-all; every unknown path lands here.
    path: '/:invalidpath(.*)*',
    name: 'Invalid Page',
    component: () => import('@/pages/InvalidPage.vue'),
  },
  {
    path: '/not-permitted',
    name: 'Not Permitted',
    component: () => import('@/pages/NotPermitted.vue'),
  },
]

const handleMobileView = (componentName) => {
  return window.innerWidth < 768 ? `Mobile${componentName}` : componentName
}

let router = createRouter({
  history: createWebHistory('/crm'),
  routes,
})

router.beforeEach(async (to, from, next) => {
  router.previousRoute = from

  const { isLoggedIn, user } = sessionStore()

  // Phase 8. The auth screens render for someone with no account, so they must bypass
  // everything below — the users store, the CRM-role check, the persona wizard, all of
  // which assume a session. **First statement in the guard**, deliberately: an earlier
  // return anywhere below would be a screen an invited user cannot reach.
  //
  // A signed-in visitor is sent home instead: a login form for someone already logged in
  // is a way to end up with two sessions and no clear idea which one is current.
  if (to.meta?.isPublic) {
    return isLoggedIn && to.name === 'Login' ? next({ path: '/' }) : next()
  }

  // Phase 8. Upstream's version of this branch was `window.location.href =
  // '/login?redirect-to=/crm'` - a jump out of the SPA to a URL nothing here serves
  // (`config/urls.py` has only `admin/` and `api/`), so an unauthenticated visitor got a
  // 404 instead of a login form. That redirect was the bug, not the contract
  // (`PHASE_8_AUTH_AND_DESK.md`). `redirect` carries where they were headed, so signing
  // in returns them to it rather than to the default view.
  //
  // Decided **before** `usersStore()` exists, deliberately (docs/FINDINGS.md 33). Upstream
  // creates the store first and lets its fetch fail with a 401, which costs nothing there
  // because the page jump that follows discards it. Here the app keeps running through
  // login, so a store created now would carry that failed fetch into the session. Checking
  // the token first means a logged-out visit fetches nothing at all.
  if (!isLoggedIn) {
    return next({ name: 'Login', query: to.fullPath === '/' ? {} : { redirect: to.fullPath } })
  }

  const { users, isCrmUser, isAdmin } = usersStore()

  if (isLoggedIn && !users.fetched) {
    try {
      // Phase 8 follow-up, the safety net behind the logged-out check above. A store
      // created before login by anything other than this guard would carry a fetch that
      // answered 401: `fetched` stays false and `promise` is that rejected fetch, so
      // waiting on it again only fails again, and isCrmUser() then says no to everyone,
      // Administrator included (docs/FINDINGS.md 33). When the last attempt errored, fetch
      // again, now with a token.
      if (users.error) {
        users.reload()
      }
      await users.promise
    } catch (error) {
      console.error('Error loading users', error)
    }
  }

  const isAdminUser = isLoggedIn && (isAdmin() || user === 'Administrator')

  // Only admins who haven't finished may reach the wizard, even via direct URL.
  if (isLoggedIn && to.name === 'Onboarding') {
    try {
      if (!isAdminUser || !(await shouldCapturePersona())) {
        return next({ name: 'Home' })
      }
    } catch {
      return next({ name: 'Home' })
    }
  }

  if (
    isLoggedIn &&
    isCrmUser() &&
    !personaChecked &&
    to.name !== 'Onboarding' &&
    isAdminUser
  ) {
    personaChecked = true
    try {
      if (await shouldCapturePersona()) {
        return next({ name: 'Onboarding' })
      }
    } catch (error) {
      // fail open
    }
  }

  if (isLoggedIn && to.name !== 'Not Permitted' && !isCrmUser()) {
    next({ name: 'Not Permitted' })
  } else if (to.name === 'Home' && isLoggedIn) {
    const { views, getDefaultView } = viewsStore()
    await views.promise

    let defaultView = getDefaultView()
    if (!defaultView) {
      next({ name: 'Leads' })
      return
    }

    let { route_name, type, name, is_standard } = defaultView
    route_name = route_name || 'Leads'

    if (name && !is_standard) {
      next({
        name: route_name,
        params: { viewType: type },
        query: { view: name },
      })
    } else {
      next({ name: route_name, params: { viewType: type } })
    }
  } else if (to.matched.length === 0) {
    next({ name: 'Invalid Page' })
  } else if (['Deal', 'Lead'].includes(to.name) && !to.hash) {
    let storageKey = to.name === 'Deal' ? 'lastDealTab' : 'lastLeadTab'
    const activeTab = localStorage.getItem(storageKey) || 'activity'
    const hash = '#' + activeTab
    next({ ...to, hash })
  } else if (
    [
      'Leads',
      'Deals',
      'Contacts',
      'Organizations',
      'Notes',
      'Tasks',
      'Call Logs',
    ].includes(to.name) &&
    !to.query?.view
  ) {
    const { views, standardViews, getDefaultView } = viewsStore()
    await views.promise

    const viewType = to.params?.viewType ?? ''
    const standardViewTypes = ['list', 'kanban', 'group_by']

    if (!viewType) {
      const doctypeMap = {
        Leads: 'CRM Lead',
        Deals: 'CRM Deal',
        Contacts: 'Contact',
        Organizations: 'CRM Organization',
        Notes: 'FCRM Note',
        Tasks: 'CRM Task',
        'Call Logs': 'CRM Call Log',
      }

      const doctype = doctypeMap[to.name]
      let defaultViewType = 'list'

      let globalDefault = getDefaultView()
      if (globalDefault && globalDefault.route_name === to.name) {
        defaultViewType = globalDefault.type || 'list'
        if (globalDefault.name && !globalDefault.is_standard) {
          next({
            name: to.name,
            params: { viewType: defaultViewType },
            query: { ...to.query, view: globalDefault.name },
          })
          return
        }
      }

      for (const viewType of standardViewTypes) {
        const standardView = standardViews.value?.[doctype + ' ' + viewType]
        if (standardView?.is_default) {
          defaultViewType = viewType
          break
        }
      }

      next({
        name: to.name,
        params: { viewType: defaultViewType },
        query: to.query,
      })
    } else if (!standardViewTypes.includes(viewType)) {
      const viewNameOrLabel = viewType

      let view = views.data?.find(
        (v) => v.name == viewNameOrLabel || v.label === viewNameOrLabel,
      )

      if (view) {
        next({
          name: to.name,
          params: { viewType: view.type || 'list' },
          query: { ...to.query, view: view.name },
        })
      } else {
        next({
          name: to.name,
          params: { viewType: 'list' },
          query: to.query,
        })
      }
    } else {
      next()
    }
  } else {
    next()
  }
})

export default router
