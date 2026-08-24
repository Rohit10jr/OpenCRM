/**
 * Status colours.
 *
 * The backend stores a colour *name* (`taxonomy.py:20` — gray, blue, green, …), not a CSS
 * value, so this is a lookup rather than a computation. Full class strings and not
 * `bg-${colour}-500`, because Tailwind scans source text and would not generate a class
 * it never sees written out.
 */
const DOT: Record<string, string> = {
  gray: 'bg-gray-400',
  blue: 'bg-blue-500',
  green: 'bg-green-500',
  red: 'bg-red-500',
  pink: 'bg-pink-500',
  orange: 'bg-orange-500',
  amber: 'bg-amber-500',
  yellow: 'bg-yellow-500',
  cyan: 'bg-cyan-500',
  teal: 'bg-teal-500',
  violet: 'bg-violet-500',
  purple: 'bg-purple-500',
  black: 'bg-black',
}

export function statusDotClass(color?: string): string {
  return `inline-block h-2 w-2 shrink-0 rounded-full ${DOT[color ?? 'gray'] ?? DOT.gray}`
}
