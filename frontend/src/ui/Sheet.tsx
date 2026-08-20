import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { X } from 'lucide-react'

export interface SheetProps {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}

/**
 * A bottom sheet on a phone, a centred dialog from `md` up — one component, so a
 * flow written once behaves correctly on both.
 *
 * Built on native `<dialog>` deliberately: `showModal()` gives a focus trap, Esc
 * to dismiss, an inert background and top-layer stacking that sidesteps z-index
 * entirely. Hand-rolling those correctly is a well-known source of accessibility
 * bugs. jsdom does not implement `<dialog>`, so `src/setupTests.ts` shims it —
 * meaning the trap and Esc handling are verified in a real browser rather than
 * here, and these unit tests assert only content, labelling and the close action.
 */
export function Sheet({ open, title, onClose, children }: SheetProps) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog === null) return

    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  // Esc fires the dialog's own `cancel` event; route it through onClose so the
  // parent's state stays the single source of truth for whether the sheet is open.
  useEffect(() => {
    const dialog = ref.current
    if (dialog === null) return

    const handleCancel = (event: Event) => {
      event.preventDefault()
      onClose()
    }
    dialog.addEventListener('cancel', handleCancel)
    return () => dialog.removeEventListener('cancel', handleCancel)
  }, [onClose])

  if (!open) return null

  return (
    <dialog
      ref={ref}
      aria-label={title}
      className="
        m-0 w-full max-w-none rounded-t-2xl border border-border bg-surface p-0 text-text
        backdrop:bg-black/40
        mt-auto
        md:m-auto md:max-w-lg md:rounded-card
      "
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-base font-semibold">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="-mr-2 flex size-11 items-center justify-center rounded-control text-text-muted"
        >
          <X className="size-5" aria-hidden="true" />
        </button>
      </div>

      {/*
        Caps the sheet below the viewport so a long list scrolls inside it, and
        keeps the bottom padding clear of the iPhone home indicator.
      */}
      <div
        className="max-h-[70vh] overflow-y-auto p-4"
        style={{ paddingBottom: 'calc(1rem + env(safe-area-inset-bottom))' }}
      >
        {children}
      </div>
    </dialog>
  )
}
