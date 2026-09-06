import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Paperclip, Send } from 'lucide-react'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { useDocList } from '@/api/hooks'
import { MissingEndpoint } from '@/components/MissingEndpoint'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

/**
 * Compose an email against a record.
 *
 * **The Send button will fail.** `frappe.core.doctype.communication.email.make` is not
 * whitelisted by this backend (`BACKEND_GAPS.md` §1). Runs 1–4 refused to build this for
 * exactly that reason; run 5 builds it on instruction, wires it to the real path, and puts
 * a banner above it so the gap is visible before the click rather than after.
 *
 * Everything *around* the send is served and works: `crm.api.contact.search_emails` for
 * recipients, `crm.api.get_user_signature` for the signature, and `Email Template` rows for
 * the template picker.
 *
 * A plain textarea rather than TipTap. The Vue composer is a rich editor and the body it
 * sends is HTML; this sends text. Swapping in TipTap is a contained change once there is a
 * send endpoint to justify it — see the run report.
 */
export function EmailComposer({
  doctype,
  name,
  onSent,
}: {
  doctype: string
  name: string
  onSent?: () => void
}) {
  const queryClient = useQueryClient()
  const [to, setTo] = useState('')
  const [cc, setCc] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [showCc, setShowCc] = useState(false)

  const signature = useQuery({
    queryKey: ['user-signature'],
    queryFn: () => callGet<string>('crm.api.get_user_signature'),
    staleTime: Infinity,
  })

  const templates = useDocList<Record<string, unknown>>('Email Template', {
    fields: ['name', 'subject', 'response'],
    limit_page_length: 50,
  })

  const send = useMutation({
    mutationFn: () =>
      call('frappe.core.doctype.communication.email.make', {
        doctype,
        name,
        recipients: to,
        cc,
        subject,
        content: signature.data ? `${body}\n\n${signature.data}` : body,
        send_email: 1,
      }),
    onSuccess: () => {
      toast.success('Email sent')
      setTo('')
      setCc('')
      setSubject('')
      setBody('')
      queryClient.invalidateQueries({ queryKey: ['activities', name] })
      onSent?.()
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not send the email')),
  })

  return (
    <div className="border-t border-outline-gray-1 bg-surface-white p-3">
      <MissingEndpoint
        className="mb-3"
        what="Sending email"
        path="frappe.core.doctype.communication.email.make"
      />

      <form
        className="flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          send.mutate()
        }}
      >
        <div className="flex items-center gap-2">
          <label className="w-10 shrink-0 text-sm text-ink-gray-5" htmlFor="email-to">
            To
          </label>
          <Input
            id="email-to"
            name="to"
            type="text"
            required
            placeholder="someone@example.com, another@example.com"
            value={to}
            onChange={(event) => setTo(event.target.value)}
          />
          {!showCc ? (
            <Button type="button" variant="ghost" size="sm" onClick={() => setShowCc(true)}>
              Cc
            </Button>
          ) : null}
        </div>

        {showCc ? (
          <div className="flex items-center gap-2">
            <label className="w-10 shrink-0 text-sm text-ink-gray-5" htmlFor="email-cc">
              Cc
            </label>
            <Input
              id="email-cc"
              name="cc"
              type="text"
              value={cc}
              onChange={(event) => setCc(event.target.value)}
            />
          </div>
        ) : null}

        <div className="flex items-center gap-2">
          <label className="w-10 shrink-0 text-sm text-ink-gray-5" htmlFor="email-subject">
            Subject
          </label>
          <Input
            id="email-subject"
            name="subject"
            type="text"
            required
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
          />
        </div>

        <textarea
          name="body"
          rows={6}
          required
          placeholder="Write your message…"
          value={body}
          onChange={(event) => setBody(event.target.value)}
          className="min-h-32 resize-y rounded border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-base text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none focus:ring-2 focus:ring-ink-gray-4"
        />

        {signature.data ? (
          <p className="whitespace-pre-wrap border-l-2 border-outline-gray-2 pl-2 text-sm text-ink-gray-4">
            {signature.data}
          </p>
        ) : null}

        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="ghost" size="sm">
                Template
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="max-h-72 w-64 overflow-y-auto">
              <DropdownMenuLabel>Insert a template</DropdownMenuLabel>
              {(templates.data ?? []).map((template) => (
                <DropdownMenuItem
                  key={String(template.name)}
                  onSelect={() => {
                    // Fills both fields, because a template is a subject *and* a body and
                    // filling one silently would look like it half-worked.
                    setSubject(String(template.subject ?? ''))
                    setBody(String(template.response ?? ''))
                  }}
                >
                  {String(template.name)}
                </DropdownMenuItem>
              ))}
              {(templates.data ?? []).length === 0 ? (
                <p className="px-2 py-1.5 text-sm text-ink-gray-4">No templates yet.</p>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            title="Attaching needs upload_file, which this backend does not serve"
            disabled
          >
            <Paperclip className="h-4 w-4" />
            Attach
          </Button>

          <Button type="submit" variant="solid" className="ml-auto" loading={send.isPending}>
            <Send className="h-4 w-4" />
            Send
          </Button>
        </div>
      </form>
    </div>
  )
}
