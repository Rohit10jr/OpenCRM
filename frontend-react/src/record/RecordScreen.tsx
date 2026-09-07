import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { AlertCircle, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { callGet, errorMessage } from '@/api/client'
import { useStatuses } from '@/list/useLookups'
import { cn } from '@/lib/utils'
import { useDocSubscription } from '@/realtime/useSocket'
import { useSession } from '@/auth/session'
import { ActivityTimeline } from './ActivityTimeline'
import { CallsTab } from './CallsTab'
import { LinkedRecords, NoteRow, TaskRow } from './LinkedRecords'
import { AssignTo } from './AssignTo'
import { Attachments } from './Attachments'
import { CallButton } from './CallButton'
import { CommentBox } from './CommentBox'
import { ContactsSection } from './ContactsSection'
import { EmailComposer } from './EmailComposer'
import { LikeButton, LinkedDocs } from './LinkedDocs'
import { SidePanel } from './SidePanel'
import { SlaSection } from './SlaSection'
import { ConvertToDealButton, StatusChange } from './StatusChange'
import { useRecord } from './useRecord'
import { WhatsAppTab } from './WhatsAppTab'

/**
 * A whole record screen: header, tabs, side panel.
 *
 * **The record equivalent of `ListView`, and shared for the same reason.** `Deal.vue` is
 * 832 lines and `Contact.vue`/`Organization.vue` repeat most of its structure with a
 * different doctype; here they pass a doctype and a title field.
 *
 * The email composer, WhatsApp tab, telephony, attachments and the contacts sub-panel were
 * all absent through run 4 and are here now. Two of them call endpoints this backend does
 * not serve and will fail visibly rather than quietly: that is the run-5 policy, and each
 * one names the missing dotted path on screen. `BACKEND_GAPS.md` is the register.
 */

type Tab = { id: string; label: string }

export function RecordScreen({
  doctype,
  name,
  statusDoctype,
  titleField,
  backTo,
  backLabel,
  asideTop,
  body,
}: {
  doctype: string
  name: string
  /** e.g. `CRM Deal Status`; omitted when the doctype has no status doctype. */
  statusDoctype?: string
  /** Which field to show as the heading. Falls back to the record's name. */
  titleField?: string
  backTo: string
  backLabel: string
  /**
   * Rendered at the top of the side panel. For the one thing a doctype has that no other
   * does and that no layout describes — a contact's deals, say. Passed in rather than
   * branched on here, so this file stays doctype-agnostic.
   */
  asideTop?: React.ReactNode
  /**
   * What to show instead of the tabs on a doctype with no activity feed. An organization's
   * deals and contacts, say — the record has plenty to show, just not a timeline.
   */
  body?: React.ReactNode
}) {
  const record = useRecord(doctype, name)
  // An open record is the one place realtime earns its keep: two people editing the same
  // deal is the normal case this exists for.
  useDocSubscription(doctype, name)
  const { statuses, getStatus } = useStatuses(statusDoctype)
  const { user: sessionUser } = useSession()
  const [tab, setTab] = useState('activity')

  // The WhatsApp tab only exists where the workspace has WhatsApp; the server is the only
  // thing that knows.
  const whatsappEnabled = useQuery({
    queryKey: ['whatsapp-enabled'],
    queryFn: () => callGet<boolean>('crm.api.whatsapp.is_whatsapp_enabled'),
    staleTime: Infinity,
    retry: false,
  })

  const doc = record.doc as Record<string, unknown> | undefined

  // Comments arrive inside the activity feed rather than from their own endpoint
  // (`activities.py:259`), so the Comments tab is a filter over what is already fetched.
  const comments = record.activities.filter((entry) => entry.activity_type === 'comment')
  const emails = record.activities.filter(
    (entry) => entry.activity_type === 'communication',
  )

  // Only deals and leads have an activity feed. A contact showing six empty tabs would
  // read as a record with no history rather than a doctype the endpoint does not serve.
  const tabs: Tab[] = record.hasActivities
    ? [
        { id: 'activity', label: 'Activity' },
        { id: 'emails', label: `Emails (${emails.length})` },
        { id: 'comments', label: `Comments (${comments.length})` },
        { id: 'calls', label: `Calls (${record.calls.length})` },
        { id: 'tasks', label: `Tasks (${record.tasks.length})` },
        { id: 'notes', label: `Notes (${record.notes.length})` },
        { id: 'attachments', label: `Attachments (${record.attachments.length})` },
        // Only when the server says the integration is live — the Vue app does the same,
        // and a WhatsApp tab on a workspace without WhatsApp is a dead end.
        ...(whatsappEnabled.data ? [{ id: 'whatsapp', label: 'WhatsApp' }] : []),
      ]
    : []

  function saveField(fieldname: string, value: unknown) {
    record.updateField.mutate(
      { fieldname, value },
      {
        // A silent failure here is the worst outcome: the input keeps showing the value
        // the user typed while the server still holds the old one.
        onError: (error) => toast.error(errorMessage(error, `Could not save ${fieldname}`)),
      },
    )
  }

  const tabBodies: Record<string, React.ReactNode> = {
    activity: (
      <ActivityTimeline
        activities={record.activities}
        isPending={record.activitiesPending}
      />
    ),
    comments: (
      <ActivityTimeline
        activities={comments}
        isPending={record.activitiesPending}
        emptyText="No comments yet."
      />
    ),
    calls: <CallsTab rows={record.calls} />,
    tasks: (
      <LinkedRecords
        doctype="CRM Task"
        label="Task"
        rows={record.tasks}
        parentDoctype={doctype}
        parentName={name}
        emptyText="No tasks yet."
        render={(row) => <TaskRow row={row} />}
      />
    ),
    notes: (
      <LinkedRecords
        doctype="FCRM Note"
        label="Note"
        rows={record.notes}
        parentDoctype={doctype}
        parentName={name}
        emptyText="No notes yet."
        render={(row) => <NoteRow row={row} />}
      />
    ),
    attachments: <Attachments name={name} rows={record.attachments} />,
    emails: (
      <div className="flex h-full flex-col">
        {/* The thread, then the composer. Emails come down inside `get_activities` as
            `communication` entries, so this is a filter over what is already fetched —
            the same trick the Comments tab uses. */}
        <div className="min-h-0 flex-1 overflow-auto">
          <ActivityTimeline
            activities={emails}
            isPending={record.activitiesPending}
            emptyText="No emails on this record yet."
          />
        </div>
        <EmailComposer doctype={doctype} name={name} />
      </div>
    ),
    whatsapp: <WhatsAppTab name={name} />,
  }

  if (record.error) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-ink-gray-4">
        <AlertCircle className="h-4 w-4" />
        {errorMessage(record.error, 'Could not load this record')}
      </div>
    )
  }

  if (record.isPending || !doc) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-ink-gray-4">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading…
      </div>
    )
  }

  const title = String((titleField && doc[titleField]) || doc.name || name)
  const status = doc.status ? String(doc.status) : ''

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-3">
        <nav className="flex min-w-0 items-center gap-1.5 text-base">
          <Link to={backTo} className="text-ink-gray-5 hover:text-ink-gray-7">
            {backLabel}
          </Link>
          <span className="text-ink-gray-4">/</span>
          <span className="truncate font-semibold text-ink-gray-8">{title}</span>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <LikeButton
            doctype={doctype}
            name={name}
            likedBy={doc._liked_by}
            currentUser={sessionUser}
          />
          <CallButton phone={doc.mobile_no ?? doc.phone} />
          <AssignTo doctype={doctype} name={name} assignees={record.assignees} />

          {doctype === 'CRM Lead' ? <ConvertToDealButton leadId={name} /> : null}

          {statusDoctype && status ? (
            <StatusChange
              statuses={statuses}
              current={status}
              colour={getStatus(status)?.color}
              isSaving={record.updateField.isPending}
              // A patch, not one field: moving to a Lost status carries the reason and
              // notes with it, and the model refuses the status without them.
              onChange={(patch) =>
                Object.entries(patch).forEach(([fieldname, value]) =>
                  saveField(fieldname, value),
                )
              }
            />
          ) : null}
        </div>
      </header>

      {/* Stacked below `xl`, side by side above it. A 384px panel beside the timeline
          leaves nothing for the timeline on a laptop, let alone a phone. */}
      <div className="flex min-h-0 flex-1 flex-col overflow-auto xl:flex-row xl:overflow-hidden">
        <div className="flex min-w-0 flex-1 flex-col">
          <div
            role="tablist"
            className={cn(
              'flex shrink-0 gap-5 overflow-x-auto px-5',
              tabs.length && 'border-b border-outline-gray-1',
            )}
          >
            {tabs.map((option) => (
              <button
                key={option.id}
                role="tab"
                aria-selected={tab === option.id}
                onClick={() => setTab(option.id)}
                className={cn(
                  'border-b-2 py-2.5 text-base text-ink-gray-5 hover:text-ink-gray-8',
                  tab === option.id
                    ? 'border-ink-gray-8 font-medium text-ink-gray-8'
                    : 'border-transparent',
                )}
              >
                {option.label}
              </button>
            ))}
          </div>

          {/* Stacked, the outer column is what scrolls; side by side, this pane does.
              A pane with `min-h-0 flex-1` inside a scrolling column collapses to nothing. */}
          <div className="flex-1 xl:min-h-0 xl:overflow-auto">
            {record.hasActivities ? (
              // A lookup rather than a ternary chain: this was five branches when it was
              // written, six once comments arrived, and a chain that long stops being
              // readable well before it stops working.
              (tabBodies[tab] ?? tabBodies.activity)
            ) : (
              (body ?? (
                <div className="flex h-full items-center justify-center p-10 text-base text-ink-gray-4">
                  This doctype has no activity feed. Edit its fields in the panel.
                </div>
              ))
            )}
          </div>

          {/* Only where a comment can actually be written. */}
          {record.hasActivities && (tab === 'activity' || tab === 'comments') ? (
            <CommentBox doctype={doctype} name={name} onAdded={() => setTab('comments')} />
          ) : null}
        </div>

        <aside className="shrink-0 border-t border-outline-gray-1 xl:w-96 xl:overflow-y-auto xl:border-l xl:border-t-0">
          {/* Above the layout, not inside it: the SLA fields are not on the side-panel
              layout the server returns, so no metadata would have placed them. */}
          <SlaSection doc={doc} onUpdateField={saveField} />
          {asideTop}
          <SidePanel
            sections={record.sections}
            doc={record.doc as never}
            onFieldChange={saveField}
            isSaving={record.updateField.isPending}
            customSections={
              doctype === 'CRM Deal'
                ? { contacts_section: <ContactsSection dealId={name} /> }
                : undefined
            }
          />
          <LinkedDocs doctype={doctype} name={name} />
        </aside>
      </div>
    </div>
  )
}
