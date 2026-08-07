import { useEffect, useRef } from 'react'

const focusableSelector = [
  'button:not(:disabled)',
  'input:not(:disabled)',
  'select:not(:disabled)',
  'textarea:not(:disabled)',
  '[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

export function useDialogFocus<ElementType extends HTMLElement>(): React.RefObject<ElementType | null> {
  const dialogRef = useRef<ElementType>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : undefined
    const preferred = dialog.querySelector<HTMLElement>('[data-autofocus]')
    const first = preferred ?? dialog.querySelector<HTMLElement>(focusableSelector)
    ;(first ?? dialog).focus()

    const keepFocusInside = (event: KeyboardEvent): void => {
      if (event.key !== 'Tab') return
      const focusable = [...dialog.querySelectorAll<HTMLElement>(focusableSelector)]
      if (focusable.length === 0) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const firstItem = focusable[0]
      const lastItem = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault()
        lastItem.focus()
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault()
        firstItem.focus()
      }
    }

    dialog.addEventListener('keydown', keepFocusInside)
    return () => {
      dialog.removeEventListener('keydown', keepFocusInside)
      previouslyFocused?.focus()
    }
  }, [])

  return dialogRef
}
