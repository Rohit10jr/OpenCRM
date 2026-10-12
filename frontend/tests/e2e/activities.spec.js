// Notes, tasks and call logs: created and edited through the shared doctype dialog,
// which reads the seeded Quick Entry layouts (docs/FINDINGS.md 43).
import { test, expect } from './fixtures.js'
import { uniqueName } from './helpers.js'

test('Create Task through the dialog adds a row that opens for editing', async ({ page, api }) => {
  await page.goto('/crm/tasks')
  await page.getByRole('button', { name: 'Create' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Create Task' })).toBeVisible()

  const title = uniqueName('E2E task')
  await dialog.getByRole('textbox', { name: 'Title', exact: true }).fill(title)
  await dialog.getByRole('button', { name: 'Create' }).click()
  await expect(dialog).toBeHidden()

  const row = page.getByText(title, { exact: true })
  await expect(row).toBeVisible()
  const [task] = await api.list('CRM Task', { filters: { title } })
  expect(task, 'the task row in the database').toBeTruthy()
  api.track('CRM Task', task.name)

  await row.click()
  const editor = page.getByRole('dialog')
  await expect(editor.getByRole('heading', { name: 'Edit Task' })).toBeVisible()
  await expect(editor.getByRole('button', { name: 'Update' })).toBeVisible()
})

test('Create Note through the dialog adds a card', async ({ page, api }) => {
  await page.goto('/crm/notes')
  await page.getByRole('button', { name: 'Create' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Create Note' })).toBeVisible()

  const title = uniqueName('E2E note')
  await dialog.getByRole('textbox', { name: 'Title', exact: true }).fill(title)
  await dialog.locator('[contenteditable="true"]').first().fill('Written by the browser test.')
  await dialog.getByRole('button', { name: 'Create' }).click()
  await expect(dialog).toBeHidden()

  await expect(page.getByText(title, { exact: true })).toBeVisible()
  const [note] = await api.list('FCRM Note', { filters: { title } })
  expect(note, 'the note row in the database').toBeTruthy()
  api.track('FCRM Note', note.name)
})

test('a call log opens its details from the list', async ({ page, api }) => {
  const to = `+1 555 ${Date.now().toString().slice(-7)}`
  await api.create('CRM Call Log', {
    type: 'Outgoing',
    status: 'Completed',
    from: '+1 555 0100',
    to,
    duration: 120,
    caller: 'Administrator',
  })
  await page.goto('/crm/call-logs')
  await page.getByText(to).first().click()
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'Call Details' })).toBeVisible()
})
