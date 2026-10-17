import { vi } from 'vitest'

const { setupScript, createDocumentResource } = vi.hoisted(() => ({
  setupScript: vi.fn(async () => []),
  createDocumentResource: vi.fn(({ doctype, name }) => ({
    doc: { doctype, name, saved_value: 'keep me' },
    save: { submit: vi.fn() },
  })),
}))

vi.mock('@/data/script', () => ({
  getScript: () => ({ setupScript, scripts: [] }),
}))
vi.mock('@/stores/global', () => ({
  globalStore: () => ({ makeCall: vi.fn() }),
}))
vi.mock('@/stores/meta', () => ({
  getMeta: () => ({ doctypesMeta: {} }),
}))
vi.mock('@/composables/useAttachments', () => ({
  useAttachments: () => ({
    trackOldFile: vi.fn(),
    processPendingDeletions: vi.fn(),
  }),
}))
vi.mock('@/composables/settings', () => ({
  showSettings: { value: false },
  activeSettingsPage: { value: null },
}))
vi.mock('@/utils', () => ({
  runSequentially: async (tasks) => {
    for (const task of tasks) await task()
  },
  parseAssignees: vi.fn(),
  sanitizeText: (value) => value,
}))
vi.mock('@/utils/fieldTransforms', () => ({
  findMissingMandatory: () => [],
}))
vi.mock('frappe-ui', async () => {
  const { reactive } = await import('vue')
  return {
    createDocumentResource,
    createResource: vi.fn(() => reactive({ data: null })),
    toast: { error: vi.fn(), success: vi.fn() },
  }
})

import { useDocument } from '@/data/document'

describe('resetDocument', () => {
  it('clears a new document in place and restores its identity fields', async () => {
    const { document, resetDocument } = useDocument('CRM Deal')
    const originalDoc = document.doc
    Object.assign(document.doc, {
      organization: 'Old Organization',
      website: 'https://old.example',
    })

    await resetDocument()

    expect(document.doc).toBe(originalDoc)
    expect(document.doc).toEqual({
      __newDocument: true,
      doctype: 'CRM Deal',
    })
  })

  it("runs the form script's onLoad again after reset", async () => {
    let onLoadCalls = 0
    setupScript.mockImplementationOnce(async (document) => [
      {
        _className: 'ResetTestDeal',
        onLoad() {
          onLoadCalls += 1
          document.doc.script_default = 'from onLoad'
        },
      },
    ])
    const { document, resetDocument } = useDocument('Reset Test Deal')
    await vi.waitFor(() => expect(onLoadCalls).toBe(1))
    document.doc.script_default = 'changed'

    await resetDocument()

    expect(onLoadCalls).toBe(2)
    expect(document.doc.script_default).toBe('from onLoad')
  })

  it('does nothing to a saved document', async () => {
    const { document, resetDocument } = useDocument('CRM Deal', 'X')
    const originalDoc = document.doc

    await resetDocument()

    expect(document.doc).toBe(originalDoc)
    expect(document.doc).toEqual({
      doctype: 'CRM Deal',
      name: 'X',
      saved_value: 'keep me',
    })
  })
})
