import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * shadcn's Button, with the variant names the Vue app uses.
 *
 * `frappe-ui`'s Button takes `variant="solid" | "subtle" | "outline" | "ghost"`; shadcn
 * ships `default | destructive | outline | secondary | ghost | link`. The ported markup
 * is full of `variant="solid"`, so the variant list below keeps frappe-ui's names rather
 * than renaming ~15 call sites to say the same thing differently.
 */
const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded text-base font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-gray-4 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        solid: 'bg-ink-gray-8 text-white hover:bg-ink-gray-7',
        subtle: 'bg-surface-gray-2 text-ink-gray-8 hover:bg-surface-gray-3',
        outline:
          'border border-outline-gray-2 bg-surface-white text-ink-gray-8 hover:bg-surface-gray-1',
        ghost: 'text-ink-gray-7 hover:bg-surface-gray-2',
        danger: 'bg-red-600 text-white hover:bg-red-700',
      },
      size: {
        sm: 'h-7 px-2 text-sm',
        md: 'h-8 px-3',
        lg: 'h-10 px-4',
        icon: 'h-7 w-7 p-0',
      },
    },
    defaultVariants: { variant: 'subtle', size: 'md' },
  },
)

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
    loading?: boolean
  }

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, loading, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        disabled={disabled || loading}
        {...props}
      >
        {/* Radix's Slot takes exactly one child, so `asChild` and `loading` do not
            compose — an `asChild` button is a link, which has nothing to load. */}
        {asChild ? (
          children
        ) : (
          <>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {children}
          </>
        )}
      </Comp>
    )
  },
)
Button.displayName = 'Button'

export { buttonVariants }
