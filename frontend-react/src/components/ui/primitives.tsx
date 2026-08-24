import * as React from 'react'
import * as AvatarPrimitive from '@radix-ui/react-avatar'
import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as PopoverPrimitive from '@radix-ui/react-popover'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { Check, X } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * The remaining shadcn primitives the list screens need: Tooltip (20 sites in Vue),
 * Dialog (15), Avatar (14), Switch (11), Popover (10), Badge (9), plus Checkbox for row
 * selection.
 *
 * One file rather than six: each is a dozen lines of the standard shadcn recipe, and
 * splitting them costs six imports per screen to buy nothing. The bigger ones — Button,
 * Input, DropdownMenu — are still their own files.
 */

// ---------------------------------------------------------------- Tooltip

export const TooltipProvider = TooltipPrimitive.Provider

/**
 * Trigger and content in one component. Every one of the 20 Vue call sites is
 * `<Tooltip :text="..."><thing/></Tooltip>`, and reproducing shadcn's four-part
 * composition at each of them would be more ceremony than the usage justifies.
 */
export function Tooltip({
  text,
  children,
  side = 'top',
}: {
  text?: React.ReactNode
  children: React.ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
}) {
  if (!text) return <>{children}</>
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={4}
          className="z-50 rounded bg-ink-gray-9 px-2 py-1 text-sm text-white shadow"
        >
          {text}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  )
}

// ---------------------------------------------------------------- Dialog

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close

export const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & { title?: string }
>(({ className, children, title, ...props }, ref) => (
  <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/40" />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        'fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-xl bg-surface-white p-5 shadow-xl',
        className,
      )}
      {...props}
    >
      {title ? (
        <div className="mb-4 flex items-center justify-between">
          <DialogPrimitive.Title className="text-lg font-semibold text-ink-gray-8">
            {title}
          </DialogPrimitive.Title>
          <DialogPrimitive.Close className="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2">
            <X className="h-4 w-4" />
          </DialogPrimitive.Close>
        </div>
      ) : null}
      {children}
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
))
DialogContent.displayName = 'DialogContent'

// ---------------------------------------------------------------- Popover

export const Popover = PopoverPrimitive.Root
export const PopoverTrigger = PopoverPrimitive.Trigger

export const PopoverContent = React.forwardRef<
  React.ElementRef<typeof PopoverPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = 'start', sideOffset = 4, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      className={cn(
        'z-50 rounded-lg border border-outline-gray-1 bg-surface-white p-3 shadow-lg',
        className,
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
))
PopoverContent.displayName = 'PopoverContent'

// ---------------------------------------------------------------- Avatar

export function Avatar({
  image,
  label,
  size = 'md',
  className,
}: {
  image?: string | null
  label?: string | null
  size?: 'xs' | 'sm' | 'md'
  className?: string
}) {
  const sizes = { xs: 'h-4 w-4 text-[8px]', sm: 'h-5 w-5 text-[10px]', md: 'h-6 w-6 text-xs' }
  return (
    <AvatarPrimitive.Root
      className={cn(
        'inline-flex shrink-0 overflow-hidden rounded-full bg-surface-gray-3',
        sizes[size],
        className,
      )}
    >
      {image ? (
        <AvatarPrimitive.Image src={image} alt={label ?? ''} className="h-full w-full object-cover" />
      ) : null}
      <AvatarPrimitive.Fallback className="flex h-full w-full items-center justify-center font-medium uppercase text-ink-gray-6">
        {(label ?? '?').charAt(0)}
      </AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  )
}

// ---------------------------------------------------------------- Switch

export const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitive.Root
    ref={ref}
    className={cn(
      'inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors data-[state=checked]:bg-ink-gray-8 data-[state=unchecked]:bg-surface-gray-4',
      className,
    )}
    {...props}
  >
    <SwitchPrimitive.Thumb className="block h-3 w-3 translate-x-0.5 rounded-full bg-white transition-transform data-[state=checked]:translate-x-3.5" />
  </SwitchPrimitive.Root>
))
Switch.displayName = 'Switch'

// ---------------------------------------------------------------- Checkbox

export const Checkbox = React.forwardRef<
  React.ElementRef<typeof CheckboxPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>
>(({ className, ...props }, ref) => (
  <CheckboxPrimitive.Root
    ref={ref}
    className={cn(
      'flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border border-outline-gray-3 text-white data-[state=checked]:border-ink-gray-8 data-[state=checked]:bg-ink-gray-8',
      className,
    )}
    {...props}
  >
    <CheckboxPrimitive.Indicator>
      <Check className="h-3 w-3" />
    </CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
))
Checkbox.displayName = 'Checkbox'

// ---------------------------------------------------------------- Badge

const badgeTheme: Record<string, string> = {
  gray: 'bg-surface-gray-3 text-ink-gray-7',
  blue: 'bg-blue-100 text-blue-800',
  green: 'bg-green-100 text-green-800',
  orange: 'bg-orange-100 text-orange-800',
  red: 'bg-red-100 text-red-800',
}

export function Badge({
  label,
  theme = 'gray',
  className,
}: {
  label: React.ReactNode
  theme?: string
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-1.5 py-0.5 text-sm font-medium',
        badgeTheme[theme] ?? badgeTheme.gray,
        className,
      )}
    >
      {label}
    </span>
  )
}
