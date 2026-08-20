type ClassValue = string | false | null | undefined

/** Join conditional class names, dropping anything falsy. */
export function cx(...values: ClassValue[]): string {
  return values.filter(Boolean).join(' ')
}
