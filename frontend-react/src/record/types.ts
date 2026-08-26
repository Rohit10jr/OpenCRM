/**
 * Wire shapes for the record screen, transcribed from the backend.
 *
 * `get_sidepanel_sections` (`crm_app/api/fields_layout.py:213`) returns the stored layout
 * with each fieldname expanded into a full descriptor, so the panel is metadata-driven —
 * it renders whatever the layout says, for any doctype, with no per-doctype code.
 */

/** One field, as `get_field_obj` expands it. */
/** One `Select` choice, as this port's field metadata serialises them. */
export type SelectChoice = { label: string; value: string }

export type PanelField = {
  fieldname: string
  fieldtype: string
  label: string
  /**
   * A string for `Link` — the target doctype.
   *
   * For `Select` it is an **array of `{label, value}`**, which is where this port diverges
   * from Frappe: upstream sends the choices newline-joined in the same field, and code
   * written against that (including the first draft of `SelectInput`) calls `.split` on an
   * array and takes the screen down. Both shapes are accepted below.
   */
  options?: string | SelectChoice[]
  placeholder?: string
  read_only?: boolean | number
  mandatory?: boolean | number
}

export type PanelColumn = {
  name: string
  label?: string
  fields: PanelField[]
}

export type PanelSection = {
  name: string
  label?: string
  opened?: boolean
  editable?: boolean
  hideBorder?: boolean
  hideLabel?: boolean
  columns?: PanelColumn[]
  /**
   * The Deal layout's `contacts_section` carries `contacts` instead of `columns`
   * (`crm/install.py:200`). It is a custom section the Vue page renders itself.
   */
  contacts?: unknown[]
}

/**
 * `crm.api.activities.get_activities` returns a **tuple**, which arrives as an array of
 * five arrays (`activities.py:452`). Naming the positions here is the difference between
 * this being readable and being `data[3]`.
 */
export type ActivitiesPayload = [
  activities: ActivityEntry[],
  calls: Record<string, unknown>[],
  notes: Record<string, unknown>[],
  tasks: Record<string, unknown>[],
  attachments: Record<string, unknown>[],
]

export type ActivityEntry = {
  name?: string | number
  activity_type?: string
  creation: string
  owner?: string
  data?: unknown
  other_versions?: ActivityEntry[]
  [key: string]: unknown
}
