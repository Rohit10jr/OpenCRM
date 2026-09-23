import './index.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createDialog } from './utils/dialogs'
import { initSocket } from './socket'
import router from './router'
import translationPlugin from './translation'
import App from './App.vue'

import {
  FrappeUI,
  Button,
  Input,
  TextInput,
  FormControl,
  ErrorMessage,
  Dialog,
  Alert,
  Badge,
  setConfig,
  FeatherIcon,
} from 'frappe-ui'

import { jwtRequest } from '@/auth/jwtRequest'
import { telemetryPlugin } from 'frappe-ui/frappe'
// injects the lucide SVG sprite into the DOM so the IconPicker and lucide Icons
// (used for view icons) can render from it
import { spritePlugin } from 'frappe-ui/icons'

let globalComponents = {
  Button,
  TextInput,
  Input,
  FormControl,
  ErrorMessage,
  Dialog,
  Alert,
  Badge,
  FeatherIcon,
}

// create a pinia instance
let pinia = createPinia()

let app = createApp(App)

// JWT PATCH (see ../JWT_PATCH.md): the Django port authenticates with bearer tokens
// rather than the `sid` cookie, so every resource fetch goes through a wrapper that
// attaches the header and refreshes on 401. This one line is the whole integration -
// none of the 225 createResource call sites change.
setConfig('resourceFetcher', jwtRequest)
app.use(FrappeUI)
app.use(spritePlugin)
app.use(pinia)
app.use(router)
app.use(translationPlugin)
for (let key in globalComponents) {
  app.component(key, globalComponents[key])
}
app.use(telemetryPlugin, { app_name: 'crm' })

app.config.globalProperties.$dialog = createDialog

// BOOT PATCH (see ../JWT_PATCH.md, the third deviation): upstream makes this call only
// under `yarn dev`, because its production page arrives with the boot values already
// written into the HTML by a Jinja template. The Django port serves no HTML, so this
// endpoint is the only source of `window.sysdefaults`, `window.timezone` and the rest,
// in production as much as in dev. A failed call logs and mounts anyway: an error on
// screen beats the blank page of an app that never mounted (docs/FINDINGS.md 26).
let socket
function mount() {
  socket = initSocket()
  app.config.globalProperties.$socket = socket
  app.mount('#app')
}

jwtRequest({ url: '/api/method/crm.www.crm.get_context_for_dev' })
  .then((values) => {
    for (let key in values) {
      window[key] = values[key]
    }
  })
  .catch((error) => {
    console.error('Boot values could not be loaded; mounting without them', error)
  })
  .then(mount)

if (import.meta.env.DEV) {
  window.$dialog = createDialog
}
