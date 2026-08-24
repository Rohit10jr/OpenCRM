import * as React from 'react'
import * as LabelPrimitive from '@radix-ui/react-label'
import { cn } from '@/lib/utils'

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      'h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-base text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none focus:ring-2 focus:ring-ink-gray-4 disabled:opacity-50',
      className,
    )}
    {...props}
  />
))
Input.displayName = 'Input'

export const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn('text-sm text-ink-gray-5', className)}
    {...props}
  />
))
Label.displayName = 'Label'

/**
 * `frappe-ui`'s `FormControl` — a label and an input, wired together — used at 11 sites.
 * Kept as one component rather than split, because that is how the ported pages read.
 */
export const FormControl = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement> & { label?: string }
>(({ label, id, className, ...props }, ref) => {
  const generated = React.useId()
  const inputId = id ?? generated
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {label ? <Label htmlFor={inputId}>{label}</Label> : null}
      <Input id={inputId} ref={ref} {...props} />
    </div>
  )
})
FormControl.displayName = 'FormControl'

/** `frappe-ui`'s `ErrorMessage`, used at 11 sites. */
export function ErrorMessage({ message }: { message?: string | null }) {
  if (!message) return null
  return <p className="text-sm text-red-600">{message}</p>
}
