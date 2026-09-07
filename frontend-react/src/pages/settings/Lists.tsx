import { DoctypeListSettings } from './DoctypeList'

/**
 * The five settings screens that are a list of rows plus an add/edit/remove.
 *
 * All of them go through `DoctypeListSettings` — see that file for why. What differs per
 * screen is here and only here: the doctype, the columns worth showing, and the form's
 * fields.
 *
 * **Email templates used to be the sixth and now has its own file.** Its body is HTML the
 * composer inserts verbatim, so a textarea produced plain-text emails — the one case where
 * the shared form was not merely plainer but wrong. That is the bar for leaving here: not
 * "this screen would be nicer bespoke", but "the shared form makes it incorrect".
 *
 * Field sets are taken from the models, not guessed:
 * `Email Account` (`frappe_platform/models.py:617`),
 * `CRM Service Level Agreement` (`sla.py:66`), `CRM Sales Hierarchy` (`metadata.py:257`),
 * `Facebook Lead Form` (`lead_syncing.py:73`), `CRM Form Script` (`metadata.py:126`).
 */

export function EmailAccountsSettingsPage() {
  return (
    <DoctypeListSettings
      doctype="Email Account"
      title="Email accounts"
      description="Mailboxes this workspace sends from and syncs into records."
      columns={['email_account_name', 'email_id', 'service']}
      emptyText="No mailbox is configured yet."
      fields={[
        { fieldname: 'email_account_name', label: 'Name', placeholder: 'Support' },
        { fieldname: 'email_id', label: 'Email address', type: 'email' },
        { fieldname: 'service', label: 'Service', placeholder: 'GMail' },
        { fieldname: 'enable_incoming', label: 'Receive mail', type: 'checkbox' },
        { fieldname: 'enable_outgoing', label: 'Send mail', type: 'checkbox' },
        {
          fieldname: 'create_contact',
          label: 'Create contacts',
          type: 'checkbox',
          hint: 'Make a Contact for an unknown sender.',
        },
      ]}
    />
  )
}

export function SlaSettingsPage() {
  return (
    <DoctypeListSettings
      doctype="CRM Service Level Agreement"
      title="Service levels"
      description="Response and resolution targets, and the hours they are measured in."
      columns={['name', 'apply_on', 'enabled']}
      emptyText="No service level agreements yet."
      fields={[
        { fieldname: 'service_level', label: 'Name' },
        {
          fieldname: 'apply_on',
          label: 'Applies to',
          placeholder: 'CRM Lead',
          hint: 'The doctype this agreement measures.',
        },
        { fieldname: 'enabled', label: 'Enabled', type: 'checkbox' },
      ]}
    />
  )
}

export function HierarchySettingsPage() {
  return (
    <DoctypeListSettings
      doctype="CRM Sales Hierarchy"
      title="Sales hierarchy"
      description="Who reports to whom. The permission engine walks this on every list request."
      columns={['name', 'parent_crm_sales_hierarchy']}
      emptyText="No hierarchy defined. Everyone sees only their own records."
      fields={[
        { fieldname: 'user', label: 'User', hint: 'The account this node represents.' },
        {
          fieldname: 'parent_crm_sales_hierarchy',
          label: 'Reports to',
          hint: 'Leave empty for a root. Managers see their whole subtree.',
        },
      ]}
    />
  )
}

export function LeadSyncingSettingsPage() {
  return (
    <DoctypeListSettings
      doctype="Facebook Lead Form"
      title="Lead syncing"
      description="Facebook lead forms that create leads here."
      columns={['name', 'page', 'enabled']}
      emptyText="No lead forms connected."
      fields={[
        { fieldname: 'form_name', label: 'Form name' },
        { fieldname: 'page', label: 'Facebook page' },
        { fieldname: 'enabled', label: 'Enabled', type: 'checkbox' },
      ]}
    />
  )
}

export function HomeActionsSettingsPage() {
  return (
    <DoctypeListSettings
      doctype="CRM Form Script"
      title="Home actions"
      description="Scripts the CRM runs on a form or list."
      columns={['name', 'dt', 'view', 'enabled']}
      emptyText="No form scripts."
      fields={[
        {
          fieldname: 'name',
          label: 'Name',
          hint: 'CRM Form Script is named by prompt — this is the document name.',
        },
        { fieldname: 'dt', label: 'Doctype', placeholder: 'CRM Deal' },
        { fieldname: 'view', label: 'View', placeholder: 'Form' },
        { fieldname: 'script', label: 'Script', type: 'textarea' },
        { fieldname: 'enabled', label: 'Enabled', type: 'checkbox' },
      ]}
    />
  )
}
