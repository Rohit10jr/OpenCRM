import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import type { DocRow } from '@/api/types'
import { cn } from '@/lib/utils'
import { FieldInput } from './FieldInput'
import type { PanelSection } from './types'

/**
 * The record side panel, rendered from `get_sidepanel_sections`.
 *
 * **Nothing here knows what a deal is.** The layout row in `CRM Fields Layout` decides
 * which sections exist, which fields are in them and in what order; an admin editing that
 * layout changes this panel with no code change, which is the whole point of the endpoint.
 * Contact and Organization screens get their panels from the same component.
 *
 * A section with no `columns` renders its heading and nothing else. The Deal layout's
 * `contacts_section` is exactly that — it carries `contacts` instead
 * (`crm/install.py:200`) and this conversion does not render contacts yet. Dropping the
 * section would hide a heading the Vue app shows; filling it with "nothing here yet"
 * would invent content for a section that has a real body we have not built. An empty
 * heading is the honest middle.
 */
export function SidePanel({
  sections,
  doc,
  onFieldChange,
  isSaving,
}: {
  sections: PanelSection[]
  doc: DocRow | undefined
  onFieldChange: (fieldname: string, value: unknown) => void
  isSaving?: boolean
}) {
  if (!sections.length) {
    return (
      <p className="p-5 text-sm text-ink-gray-4">
        No side panel layout is configured for this doctype.
      </p>
    )
  }

  return (
    <div className="flex flex-col">
      {sections.map((section) => (
        <Section key={section.name} section={section}>
          {section.columns?.length ? (
            section.columns.map((column) => (
              <div key={column.name} className="flex flex-col gap-1.5">
                {column.fields.map((field) => (
                  <div key={field.fieldname} className="flex items-center gap-2">
                    <label
                      className="w-32 shrink-0 truncate text-sm text-ink-gray-5"
                      htmlFor={`field-${field.fieldname}`}
                    >
                      {field.label}
                    </label>
                    <div className="min-w-0 flex-1">
                      <FieldInput
                        field={field}
                        value={doc?.[field.fieldname]}
                        disabled={isSaving}
                        onCommit={(value) => onFieldChange(field.fieldname, value)}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ))
          ) : null}
        </Section>
      ))}
    </div>
  )
}

function Section({
  section,
  children,
}: {
  section: PanelSection
  children: React.ReactNode
}) {
  // `opened` is the layout's stored default; after that it is the reader's choice.
  const [open, setOpen] = useState(section.opened ?? true)

  return (
    <section className={cn('px-4 py-3', !section.hideBorder && 'border-b border-outline-gray-1')}>
      {section.hideLabel ? null : (
        <button
          type="button"
          onClick={() => setOpen((current) => !current)}
          className="mb-2 flex w-full items-center gap-1 text-sm font-medium text-ink-gray-6"
        >
          <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-90')} />
          {section.label ?? section.name}
        </button>
      )}
      {open ? <div className="flex flex-col gap-3">{children}</div> : null}
    </section>
  )
}
