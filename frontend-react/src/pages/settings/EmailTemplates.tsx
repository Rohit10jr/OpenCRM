import { useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import { useDocList, useDocMutations } from '@/api/hooks'
import { RichTextEditor } from '@/components/RichText'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge, Dialog, DialogContent, Switch } from '@/components/ui/primitives'
import { SettingsPage } from './SettingsLayout'

/**
 * Settings → Email templates, with a real editor.
 *
 * The other five list-shaped settings screens share `DoctypeListSettings`, and this one did
 * too until the body proved to need more than a textarea: a template's `response` is HTML
 * that the composer inserts verbatim, so writing it as plain text produces a plain-text
 * email. `VUE_DIVERGENCES.md` §11 recorded that as the sharpest thing the shared form lost;
 * this closes it.
 *
 * **Two bodies, one document.** `use_html` picks between `response` (rich text) and
 * `response_html` (hand-written HTML) — both columns exist on the model
 * (`frappe_platform/models.py:544`) and the flag says which one the server should send.
 * Upstream calls the toggle "Content Type" and offers Rich Text / HTML; the stored field is
 * a boolean, so this is a switch.
 *
 * **There is no variable picker**, here or upstream — `EditEmailTemplate.vue` types
 * `{{ field }}` into the subject and body by hand and shows examples as placeholder text.
 * The hint below does the same job.
 */

type Template = {
  name: string
  subject?: string
  response?: string
  response_html?: string
  reference_doctype?: string
  use_html?: boolean | number
  enabled?: boolean | number
}

const FIELDS = [
  'name',
  'subject',
  'response',
  'response_html',
  'reference_doctype',
  'use_html',
  'enabled',
]

export function EmailTemplatesSettingsPage() {
  const [editing, setEditing] = useState<Template>()
  const [open, setOpen] = useState(false)

  const templates = useDocList<Template>('Email Template', {
    fields: FIELDS,
    limit_page_length: 100,
    order_by: 'modified desc',
  })
  const { remove } = useDocMutations('Email Template')

  const rows = templates.data ?? []

  return (
    <SettingsPage
      title="Email templates"
      description="Reusable subjects and bodies the composer can insert."
      actions={
        <Button
          variant="solid"
          onClick={() => {
            setEditing(undefined)
            setOpen(true)
          }}
        >
          <Plus className="h-4 w-4" />
          New
        </Button>
      }
    >
      {templates.isPending ? (
        <p className="text-base text-ink-gray-4">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-base text-ink-gray-4">No templates yet.</p>
      ) : (
        <ul className="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
          {rows.map((template) => (
            <li key={template.name} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-base text-ink-gray-8">{template.name}</span>
                  {template.use_html ? <Badge label="HTML" theme="gray" /> : null}
                  {template.enabled ? null : <Badge label="Disabled" theme="orange" />}
                </div>
                <p className="truncate text-sm text-ink-gray-5">
                  {[template.subject, template.reference_doctype].filter(Boolean).join(' · ')}
                </p>
              </div>

              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditing(template)
                  setOpen(true)
                }}
              >
                <Pencil className="h-4 w-4" />
                Edit
              </Button>
              <Button
                variant="ghost"
                size="icon"
                title={`Delete ${template.name}`}
                onClick={() =>
                  remove.mutate(template.name, {
                    onError: (error) =>
                      toast.error(errorMessage(error, 'Could not delete the template')),
                  })
                }
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <TemplateDialog
        key={editing?.name ?? 'new'}
        open={open}
        onOpenChange={setOpen}
        template={editing}
      />
    </SettingsPage>
  )
}

/**
 * The editor.
 *
 * Keyed on the template's name by the caller, so opening a different row remounts it with
 * fresh state rather than carrying the last one's draft across — the same trap
 * `CreateModal` solves with a re-seed, solved here the simpler way because this form is
 * not shared.
 */
function TemplateDialog({
  open,
  onOpenChange,
  template,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  template?: Template
}) {
  const editing = Boolean(template)
  const { create, update } = useDocMutations('Email Template')

  const [name, setName] = useState(template?.name ?? '')
  const [subject, setSubject] = useState(template?.subject ?? '')
  const [reference, setReference] = useState(template?.reference_doctype ?? '')
  const [useHtml, setUseHtml] = useState(Boolean(template?.use_html))
  const [response, setResponse] = useState(template?.response ?? '')
  const [responseHtml, setResponseHtml] = useState(template?.response_html ?? '')
  const [enabled, setEnabled] = useState(template?.enabled ?? true)

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const values = {
      subject,
      reference_doctype: reference,
      use_html: useHtml ? 1 : 0,
      // Both columns are written every time. The flag decides which the server sends, and
      // leaving the other stale means toggling the switch shows someone else's draft.
      response,
      response_html: responseHtml,
      enabled: enabled ? 1 : 0,
    }

    const done = (message: string) => () => {
      toast.success(message)
      onOpenChange(false)
    }

    if (template) {
      update.mutate(
        { name: template.name, changes: values },
        {
          onSuccess: done('Template saved'),
          onError: (error) => toast.error(errorMessage(error, 'Could not save the template')),
        },
      )
      return
    }

    // `Email Template` is named by prompt, so the name *is* the document id and is sent on
    // create only — renaming is a separate operation this form does not do.
    create.mutate(
      { ...values, name },
      {
        onSuccess: done('Template created'),
        onError: (error) => toast.error(errorMessage(error, 'Could not create the template')),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={editing ? `Edit ${template?.name}` : 'New email template'}
        className="max-w-2xl"
      >
        <form className="flex max-h-[70vh] flex-col gap-3 overflow-y-auto pr-1" onSubmit={submit}>
          <Field label="Name">
            <Input
              value={name}
              required
              disabled={editing}
              placeholder="Payment reminder"
              onChange={(event) => setName(event.target.value)}
            />
          </Field>

          <Field label="Applies to">
            <select
              className="h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-base"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
            >
              <option value="">Any record</option>
              <option value="CRM Deal">Deal</option>
              <option value="CRM Lead">Lead</option>
            </select>
          </Field>

          <Field label="Subject">
            <Input
              value={subject}
              required
              placeholder="Payment reminder — {{ name }}"
              onChange={(event) => setSubject(event.target.value)}
            />
          </Field>

          <p className="rounded bg-surface-gray-1 px-2 py-1.5 text-sm text-ink-gray-5">
            {/* Upstream has no picker either; it shows examples and expects you to type. */}
            Wrap a fieldname in double braces to substitute it — <code>{'{{ name }}'}</code>,{' '}
            <code>{'{{ organization }}'}</code>, <code>{'{{ lead_name }}'}</code>. The subject
            takes them too.
          </p>

          <label className="flex items-center gap-2">
            <Switch checked={useHtml} onCheckedChange={setUseHtml} />
            <span className="text-base text-ink-gray-7">Write raw HTML</span>
          </label>

          <Field label="Body">
            {useHtml ? (
              <textarea
                className="min-h-48 w-full rounded border border-outline-gray-2 bg-surface-white p-2 font-mono text-sm text-ink-gray-8"
                value={responseHtml}
                onChange={(event) => setResponseHtml(event.target.value)}
                placeholder="<p>Dear {{ lead_name }},</p>"
              />
            ) : (
              <RichTextEditor
                value={response}
                placeholder="Dear {{ lead_name }}, …"
                onChange={setResponse}
              />
            )}
          </Field>

          <label className="flex items-center gap-2">
            <Switch
              checked={Boolean(enabled)}
              onCheckedChange={(next) => setEnabled(next)}
            />
            <span className="text-base text-ink-gray-7">Enabled</span>
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="subtle" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="solid"
              loading={create.isPending || update.isPending}
            >
              {editing ? 'Save' : 'Create'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm text-ink-gray-5">{label}</span>
      {children}
    </label>
  )
}
