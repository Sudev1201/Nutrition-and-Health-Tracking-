import { expect, test } from '@playwright/test'

/**
 * Onboarding -> log -> dashboard, against the real backend.
 *
 * What this catches that the component tests cannot:
 *
 *  - The real ICMR energy chain. A jsdom test asserting 2,110 kcal is asserting
 *    its own fixture; here the number comes out of the profile the browser just
 *    saved, through the reference tables, out of FastAPI.
 *  - `AppShell` renders both layouts into the DOM at once and switches on a CSS
 *    breakpoint, so every secondary nav link exists twice at any viewport. That
 *    is invisible to jsdom and trips Playwright's strict mode, which is why the
 *    selectors below are scoped rather than global.
 *  - `Sheet` uses a native <dialog>, whose focus trap and Esc handling jsdom does
 *    not implement at all — `setupTests.ts` shims them and says outright that
 *    they are verified manually. This is the first automated check of the real
 *    thing.
 */

const SEARCH_DEBOUNCE_MS = 400

test.describe('the tracking loop', () => {
  test('a new user can onboard, log a meal and see it on the dashboard', async ({ page }) => {
    // --- onboarding ---------------------------------------------------------
    await page.goto('/profile/about')

    await expect(page.getByRole('heading', { name: 'About you' })).toBeVisible()

    await page.getByLabel('Sex').selectOption('male')
    await page.getByLabel('Age').fill('25')
    await page.getByLabel(/weight in kg/i).fill('65')
    await page.getByLabel(/activity level/i).selectOption('sedentary')
    await page.getByRole('button', { name: 'Continue' }).click()

    await expect(page.getByRole('heading', { name: 'Your goal' })).toBeVisible()
    await page.getByLabel(/aiming for/i).selectOption('maintain')
    await page.getByRole('button', { name: 'Continue' }).click()

    await expect(page.getByRole('heading', { name: 'How you eat' })).toBeVisible()
    await page.getByLabel(/how do you eat/i).selectOption('vegetarian')
    await page.getByRole('button', { name: 'Continue' }).click()

    // The remaining five steps are all optional, so they are walked rather than
    // filled: the point here is that the wizard completes and saves.
    for (const title of [
      'Health conditions',
      'Vegetarian days',
      'Foods you like and avoid',
      'When you eat',
    ]) {
      await expect(page.getByRole('heading', { name: title })).toBeVisible()
      await page.getByRole('button', { name: 'Continue' }).click()
    }

    await expect(page.getByRole('heading', { name: 'What you usually eat' })).toBeVisible()
    await page.getByRole('button', { name: /finish|save changes/i }).click()

    // --- the dashboard, computed by the real engine -------------------------
    await page.waitForURL('**/profile')

    await page.goto('/')
    // ~2,110 kcal for a 25-year-old 65 kg sedentary man, straight out of the
    // FAO/WHO/UNU equations and ICMR's body-composition correction. The comma is
    // en-IN grouping from `formatAmount`.
    await expect(page.getByText(/2,1\d\d/).first()).toBeVisible()

    // --- logging a real dish from the seeded database -----------------------
    await page.goto('/log?slot=lunch')

    const search = page.getByRole('searchbox', { name: /search/i })
    // "curd" rather than a dish: `scripts/e2e_seed.py` guarantees it without any
    // download, so this passes on a database that has never run the full ETL.
    await search.fill('curd')
    // `SearchField` debounces, so results are awaited rather than assumed.
    await page.waitForTimeout(SEARCH_DEBOUNCE_MS)

    const firstResult = page.getByRole('button', { name: /^Add / }).first()
    await expect(firstResult).toBeVisible()
    const addedName = ((await firstResult.getAttribute('aria-label')) ?? '').replace(/^Add /, '')
    await firstResult.click()

    // The portion sheet is a native <dialog>; this is the part jsdom cannot test.
    const sheet = page.getByRole('dialog')
    await expect(sheet).toBeVisible()

    await page.getByRole('button', { name: /add to/i }).click()

    // The sheet closing is the success signal. Logging deliberately stays on
    // /log so a second item can be added without navigating back, so there is
    // no URL change to wait for here.
    await expect(sheet).toBeHidden()

    // --- it shows up on Today ----------------------------------------------
    await page.goto('/')

    await expect(page.getByText(addedName, { exact: false }).first()).toBeVisible()
  })

  test('a meal can be skipped, and the slot says so rather than reading as empty', async ({
    page,
  }) => {
    await page.goto('/')

    // Dinner, not lunch: globalSetup resets the user once per run rather than
    // per test, so the walk above has already logged into lunch and its slot is
    // no longer empty. Each test owns a different slot to stay independent of
    // the others' order.
    //
    // Each Skip button names its own slot ("Skip dinner"), which is what makes
    // it addressable without scoping. The nav is the part that renders twice at
    // any viewport -- AppShell puts both layouts in the DOM and switches on a
    // CSS breakpoint -- so anything matched there would need a landmark.
    const skipDinner = page.getByRole('button', { name: 'Skip dinner' })
    await expect(skipDinner).toBeVisible()
    await skipDinner.click()

    await expect(page.getByText(/Skipped —/).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /log it after all/i }).first()).toBeVisible()
  })

  test('the escape key closes the portion sheet', async ({ page }) => {
    // Native <dialog> behaviour: a focus trap, Esc-to-dismiss, an inert
    // background. jsdom implements none of it, so this is the only place it is
    // actually checked.
    await page.goto('/log?slot=lunch')

    await page.getByRole('searchbox', { name: /search/i }).fill('sugar')
    await page.waitForTimeout(SEARCH_DEBOUNCE_MS)

    await page.getByRole('button', { name: /^Add / }).first().click()
    await expect(page.getByRole('dialog')).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toBeHidden()
  })
})
