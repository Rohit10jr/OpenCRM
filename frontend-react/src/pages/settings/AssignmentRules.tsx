import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy } from 'lucide-react'
import { toast } from 'sonner'
import { call, callGet, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/primitives'
import { SettingsPage } from './SettingsLayout'

/**
 * Assignment rules — who a new lead or deal lands on.
 *
 * Not built on `DoctypeListSettings`, because this one has its own endpoints rather than
 * plain CRUD: `crm.api.assignment_rule.get_assignment_rules_list` returns the rules already
 * joined to their doctype and user set, and `duplicate_assignment_rule` is the server's own
 * clone — the usual way to make a rule is to copy a working one.
 *
 * Creating a rule from nothing is not built here. Upstream opens a multi-step editor for it
 * (conditions, a day/hour schedule, a user list), which is a screen of its own rather than a
 * dialog. Duplicating covers the common case and is honest about the rest.
 */
export function AssignmentRulesSettingsPage() {
  const queryClient = useQueryClient()

  const rules = useQuery({
    queryKey: ['assignment-rules'],
    queryFn: () =>
      callGet<Record<string, unknown>[]>('crm.api.assignment_rule.get_assignment_rules_list'),
    retry: false,
  })

  const duplicate = useMutation({
    mutationFn: (name: string) =>
      call('crm.api.assignment_rule.duplicate_assignment_rule', { name }),
    onSuccess: () => {
      toast.success('Rule duplicated')
      queryClient.invalidateQueries({ queryKey: ['assignment-rules'] })
    },
    onError: (error) => toast.error(errorMessage(error, 'Could not duplicate')),
  })

  const list = rules.data ?? []

  return (
    <SettingsPage
      title="Assignment rules"
      description="Which salesperson a new record is assigned to, and on what schedule."
    >
      {rules.isPending ? (
        <p className="text-base text-ink-gray-4">Loading…</p>
      ) : rules.isError ? (
        <p className="text-base text-ink-gray-4">Could not read assignment rules.</p>
      ) : list.length === 0 ? (
        <p className="text-base text-ink-gray-4">
          No rules yet. New records stay unassigned until someone picks them up.
        </p>
      ) : (
        <ul className="divide-y divide-outline-gray-1 border-y border-outline-gray-1">
          {list.map((rule, index) => (
            <li key={String(rule.name ?? index)} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 truncate text-base text-ink-gray-8">
                  {String(rule.label ?? rule.name)}
                  {rule.disabled ? (
                    <Badge label="Disabled" theme="gray" />
                  ) : (
                    <Badge label="Active" theme="green" />
                  )}
                </p>
                <p className="truncate text-sm text-ink-gray-5">
                  {[rule.document_type, rule.assign_condition]
                    .filter(Boolean)
                    .map(String)
                    .join(' · ')}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                loading={duplicate.isPending}
                onClick={() => duplicate.mutate(String(rule.name))}
              >
                <Copy className="h-4 w-4" />
                Duplicate
              </Button>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-5 text-sm text-ink-gray-4">
        Creating a rule from scratch is not built yet — upstream opens a multi-step editor
        for conditions, schedule and user set. Duplicate an existing rule and edit it in the
        backend for now.
      </p>
    </SettingsPage>
  )
}
