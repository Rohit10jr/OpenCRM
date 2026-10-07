import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import path from 'path'
import { VitePWA } from 'vite-plugin-pwa'

// https://vitejs.dev/config/
export default defineConfig(async ({ mode }) => {
  const isDev = mode === 'development'
  // The Django server's port; frappe-ui's proxy plugin reads the same variable.
  const backendPort = Number(process.env.FRAPPE_WEB_SERVER_PORT) || 8000
  const config = {
    plugins: [
      vue(),
      vueJsx(),
      VitePWA({
        registerType: 'autoUpdate',
        devOptions: {
          enabled: true,
        },
        manifest: {
          display: 'standalone',
          name: 'Frappe CRM',
          short_name: 'Frappe CRM',
          start_url: '/crm',
          description:
            'Modern & 100% Open-source CRM tool to supercharge your sales operations',
          icons: [
            {
              src: '/assets/crm/manifest/manifest-icon-192.maskable.png',
              sizes: '192x192',
              type: 'image/png',
              purpose: 'any',
            },
            {
              src: '/assets/crm/manifest/manifest-icon-192.maskable.png',
              sizes: '192x192',
              type: 'image/png',
              purpose: 'maskable',
            },
            {
              src: '/assets/crm/manifest/manifest-icon-512.maskable.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'any',
            },
            {
              src: '/assets/crm/manifest/manifest-icon-512.maskable.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'maskable',
            },
          ],
        },
      }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
        // point at the package src dir (not index.ts) so subpath imports like
        // `@framework/ui/components/Notifications` resolve. Importing subpaths avoids the
        // barrel, which `export *`s components (Grid/Phone/FormLayout) that need a newer
        // frappe-ui (`frappe-ui/internals`) than this app pins.
        '@framework/ui': path.resolve(__dirname, '../../frappe/ui/src'),
      },
      // ensure the linked framework package reuses the host app's single copy of each peer.
      // `dompurify` is an implicit dep of @framework/ui's sanitize util (not declared in its
      // package.json); dedupe resolves it to the host's copy since the symlinked source has
      // no node_modules of its own.
      // the editor packages must resolve to one copy each: tiptap imports
      // `@tiptap/pm/model` while prosemirror-state/transform/tables import bare
      // `prosemirror-model`, so a nested install of either throws "multiple
      // versions of prosemirror-model were loaded" on mention insert. Unlike
      // optimizeDeps (dev-only) this also applies to the production build.
      dedupe: [
        'vue',
        'vue-router',
        'frappe-ui',
        'dompurify',
        '@tiptap/core',
        '@tiptap/pm',
        '@tiptap/vue-3',
        'prosemirror-model',
        'prosemirror-state',
        'prosemirror-view',
        'prosemirror-transform',
      ],
    },
    optimizeDeps: {
      // frappe-ui ships as source and imports `~icons/lucide/*`, virtual modules that only
      // its own Vite plugin resolves; esbuild's pre-bundler cannot, so the package has to
      // be served raw. Vite then skips pre-bundling for every bare import made from inside
      // it, which is why its CommonJS dependencies must be listed under `include`.
      exclude: ['frappe-ui'],
      include: [
        'feather-icons',
        'tailwind.config.js',
        'prosemirror-state',
        'prosemirror-view',
        'lowlight',
        'interactjs',
        // Reached from frappe-ui's socketio.ts: socket.io-client -> socket.io-parser,
        // whose `development` export condition picks its debug build, which imports the
        // CommonJS `debug` package. Served raw, that import has no default export and
        // the whole bundle fails before main.js runs (docs/FINDINGS.md 27).
        'socket.io-client',
        // Every other package frappe-ui's source imports (grep `from '` under
        // node_modules/frappe-ui/src), by the exact specifier it uses. Vite never
        // pre-bundles a bare import made from inside node_modules, so without these
        // entries each one is served as raw modules: reka-ui alone is 560 files and
        // echarts 550, at ~40 ms per file here (docs/FINDINGS.md 29). Listed, each
        // becomes one pre-bundled file, and the tiptap/prosemirror family shares one
        // copy of prosemirror-model across the bundles.
        'reka-ui',
        'echarts',
        'grid-layout-plus',
        '@floating-ui/dom',
        '@floating-ui/vue',
        '@codemirror/state',
        '@codemirror/view',
        'vue-sonner',
        'tippy.js',
        'marked',
        'idb-keyval',
        'dayjs/esm',
        'dayjs/esm/plugin/utc',
        'dayjs/esm/plugin/updateLocale',
        'dayjs/esm/plugin/timezone',
        'dayjs/esm/plugin/relativeTime',
        'dayjs/esm/plugin/localizedFormat',
        'dayjs/esm/plugin/isToday',
        'dayjs/esm/plugin/duration',
        'dayjs/esm/plugin/customParseFormat',
        'dayjs/esm/plugin/advancedFormat',
        '@tiptap/core',
        '@tiptap/vue-3',
        '@tiptap/vue-3/menus',
        '@tiptap/pm/state',
        '@tiptap/pm/model',
        '@tiptap/pm/view',
        '@tiptap/pm/tables',
        '@tiptap/suggestion',
        '@tiptap/extensions',
        '@tiptap/starter-kit',
        '@tiptap/markdown',
        '@tiptap/extension-heading',
        '@tiptap/extension-link',
        '@tiptap/extension-underline',
        '@tiptap/extension-typography',
        '@tiptap/extension-text-style',
        '@tiptap/extension-text-align',
        '@tiptap/extension-text',
        '@tiptap/extension-table',
        '@tiptap/extension-strike',
        '@tiptap/extension-paragraph',
        '@tiptap/extension-list',
        '@tiptap/extension-italic',
        '@tiptap/extension-code-block-lowlight',
        '@tiptap/extension-code',
        '@tiptap/extension-bold',
        '@tiptap/extension-task-list',
        '@tiptap/extension-task-item',
        '@tiptap/extension-placeholder',
        '@tiptap/extension-horizontal-rule',
        '@tiptap/extension-hard-break',
        '@tiptap/extension-document',
        '@tiptap/extension-blockquote',
      ],
    },
    server: {
      // What frappe-ui's `frappeProxy` plugin would set, written out here because that
      // plugin never returns on Windows (docs/FINDINGS.md 48): it looks for a bench by
      // walking up the directory tree until the path equals `/`, which a Windows path
      // never does. Same port arithmetic (backend 8000 -> Vite 8080), same proxy rule
      // (upstream's list plus `ws`, see the frappeui() call below), same host-preserving
      // router, and the same FRAPPE_WEB_SERVER_PORT override.
      port: 8080 + (backendPort - 8000),
      proxy: {
        '^/(desk|app|login|api|assets|files|private|ws)': {
          target: `http://127.0.0.1:${backendPort}`,
          ws: true,
          router: (req) => `http://${req.headers.host.split(':')[0]}:${backendPort}`,
        },
      },
      fs: {
        // allow the bench `apps/` dir so Vite can serve linked local packages
        // (frappe-ui, @framework/ui) that live in sibling app repos
        allow: [path.resolve(__dirname, '../..')],
      },
    },
  }

  const frappeui = await importFrappeUIPlugin(isDev, config)
  config.plugins.unshift(
    frappeui({
      // Off: its constructor loops forever on Windows (docs/FINDINGS.md 48). The proxy
      // it would have configured is `server.proxy` above: upstream's source list plus
      // `ws`, because the port's realtime channel is a plain WebSocket at /ws/realtime
      // on the Django (daphne) server, not socket.io on port 9000, and src/socket.js
      // connects to it same-origin. Without that entry Vite answers the upgrade itself
      // and the client retries forever (frontend/JWT_PATCH.md, realtime).
      frappeProxy: false,
      // frappe-ui cannot be pre-bundled here (see optimizeDeps below), so in dev every
      // `import { X } from 'frappe-ui'` would pull the whole barrel: 3,200 modules, TipTap,
      // CodeMirror and echarts included, several minutes per cold load on this machine.
      // The plugin's rewrite to deep imports skips installed copies by default on the
      // assumption that they are pre-bundled; forcing it is what its own comment
      // recommends for a package that cannot be (docs/FINDINGS.md 29).
      barrelImports: { linkedOnly: false },
      lucideIcons: true,
      jinjaBootData: true,
      buildConfig: {
        indexHtmlPath: '../crm/www/crm.html',
        emptyOutDir: true,
        sourcemap: true,
      },
    }),
  )

  return config
})

async function importFrappeUIPlugin(isDev, config) {
  if (isDev) {
    try {
      // Check if local frappe-ui has the vite plugin file
      const fs = await import('node:fs')
      const localVitePluginPath = path.resolve(__dirname, '../frappe-ui/vite')

      if (fs.existsSync(localVitePluginPath)) {
        const module = await import('../frappe-ui/vite')
        console.info('Local frappe-ui vite plugin found, using local plugin')
        config.resolve.alias = getAliases(config)
        return module.default
      } else {
        console.warn('Local frappe-ui vite plugin not found, using npm package')
      }
    } catch (error) {
      console.warn(
        'Local frappe-ui not found, falling back to npm package:',
        error.message,
      )
    }
  }
  // Fall back to npm package if local import fails
  const module = await import('frappe-ui/vite')
  return module.default
}

function getAliases(config) {
  return {
    ...config.resolve.alias,
    'frappe-ui/tailwind': path.resolve(
      __dirname,
      '../frappe-ui/tailwind/preset.js',
    ),
    'frappe-ui/style.css': path.resolve(
      __dirname,
      '../frappe-ui/src/style.css',
    ),
    'frappe-ui/frappe': path.resolve(__dirname, '../frappe-ui/frappe/index.js'),
    // subpath entries must precede the bare `frappe-ui` key: a plain string alias
    // matches by prefix, so without these subpaths would rewrite under
    // `.../src/index.ts`. `internals` is pulled in by @framework/ui.
    'frappe-ui/icons': path.resolve(__dirname, '../frappe-ui/icons/index.ts'),
    'frappe-ui/editor': path.resolve(
      __dirname,
      '../frappe-ui/src/molecules/editor/index.ts',
    ),
    'frappe-ui/editor-style.css': path.resolve(
      __dirname,
      '../frappe-ui/src/molecules/editor/style.css',
    ),
    'frappe-ui/internals': path.resolve(__dirname, '../frappe-ui/internals.ts'),
    'frappe-ui': path.resolve(__dirname, '../frappe-ui/src/index.ts'),
  }
}
