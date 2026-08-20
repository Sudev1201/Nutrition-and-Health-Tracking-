import '@testing-library/jest-dom'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './mocks/server'

/**
 * jsdom 30 recognises `<dialog>` as an HTMLDialogElement but implements none of
 * its methods, so `showModal()` throws. `Sheet` uses native `<dialog>` on purpose
 * — it is what gives real users a focus trap, Esc-to-dismiss, an inert background
 * and top-layer stacking — so the element is shimmed here rather than the
 * component being redesigned around a test environment's gap.
 *
 * Consequence worth stating: the focus trap and Esc handling are NOT covered by
 * unit tests. They are browser behaviour, and are verified manually.
 */
if (typeof HTMLDialogElement !== 'undefined' && HTMLDialogElement.prototype.showModal === undefined) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '')
  }

  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  }
}

// `error` rather than `bypass`: in a test, a request nobody stubbed is a mistake
// worth failing on, not something to quietly send to a server that isn't running.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
