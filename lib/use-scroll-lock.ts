'use client'

import { useEffect } from 'react'

// Глобальный счётчик нужен, чтобы вложенные модальные окна
// (например, ResultSheet + окно ингредиентов) не снимали блокировку
// скрола раньше времени.
let lockCount = 0

/**
 * Блокирует прокрутку фонового контента (main), пока открыто модальное окно.
 * Добавляет класс `modal-open` на <body>; сам скролл отключается в CSS.
 */
export function useScrollLock(active: boolean) {
  useEffect(() => {
    if (!active) return

    lockCount += 1
    document.body.classList.add('modal-open')

    return () => {
      lockCount -= 1
      if (lockCount <= 0) {
        lockCount = 0
        document.body.classList.remove('modal-open')
      }
    }
  }, [active])
}
