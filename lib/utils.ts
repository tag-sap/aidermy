import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Делает первую букву заглавной, если строка начинается с буквы.
 * Не меняет регистр остальной части и не трогает строки, начинающиеся с цифры/символа.
 */
export function capitalizeFirst(value: string): string {
  if (!value) return value
  for (let i = 0; i < value.length; i++) {
    const ch = value[i]
    if (/[a-zа-яё]/i.test(ch)) return value.slice(0, i) + ch.toUpperCase() + value.slice(i + 1)
    if (!/\s/.test(ch)) return value
  }
  return value
}
