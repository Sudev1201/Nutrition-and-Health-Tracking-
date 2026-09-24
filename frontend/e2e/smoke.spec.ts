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
 *  - The Plan screen on the real planner, rather than the fixture it shipped with,
 *    and -- when the database carries the full ETL -- a swap and a lock against the
 *    real dish pool, which is the path `load_pool` runs on every edit.
 *  - Weight on the real trend: onboarding's weight is the first weigh-in, and a
 *    weigh-in the same day replaces it.
 *  - Cycle tracking gated on the profile, and a heavy-bleeding answer producing a
 *    referral rather than a changed target.
 *  - The weekly report on the real week walk: last week opens first, an empty week
 *    says so, and the week in progress is as far as it goes.
 *  - Meal reminders on the real settings endpoint: a slot switched off stays off
 *    across a reload, and the mid-morning snack starts off.
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

  test('the plan page shows a Sunday-to-Saturday week from the real planner', async ({
    page,
  }) => {
    // `scripts/e2e_seed.py` seeds no dishes with slot tags, so the plan it
    // produces is seven days with nothing in them. That is still the thing worth
    // checking: the screen is no longer on a fixture, the week comes out of
    // FastAPI Sunday to Saturday, and regenerating round-trips. Dish content
    // needs the full ETL, which is far too slow for CI.
    await page.goto('/plan')

    // Days are landmark regions named by weekday; at the default desktop
    // viewport all seven are visible side by side.
    await expect(page.getByRole('region', { name: 'Sunday' })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Saturday' })).toBeVisible()

    // The demo banner is gone for good.
    await expect(page.getByRole('note')).toHaveCount(0)

    // Wait for the regenerate's own refetch, not just the click: against the full
    // ETL this POST can still be running server-side after the test moves on, and
    // the next test's swap can then race it and hit a stale item id.
    const refetched = page.waitForResponse(
      (response) =>
        response.request().method() === 'GET' && response.url().includes('/plan/week?'),
    )
    await page.getByRole('button', { name: /regenerate week/i }).click()
    await refetched
    await expect(page.getByRole('region', { name: 'Sunday' })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })

  test('a planned dish can be swapped, and a locked one survives a regenerate', async ({
    page,
  }) => {
    await page.goto('/plan')
    await expect(page.getByRole('region', { name: 'Saturday' })).toBeVisible()

    // Only plan rows carry a Swap button, which keeps the nav's list items out of
    // the match. Against the CI seed there are none -- slot-tagged dishes come
    // only from the full ETL -- so this walk skips rather than asserting on a
    // week it knows to be blank. Locally, against a seeded database, it runs.
    const rows = page
      .getByRole('listitem')
      .filter({ has: page.getByRole('button', { name: 'Swap' }) })
    test.skip((await rows.count()) === 0, 'no slot-tagged dishes seeded; needs the full ETL')

    // The first <p> in a row is the dish name; the slot label above it is a span.
    const row = rows.first()
    const dish = row.getByRole('paragraph').first()
    const before = (await dish.textContent()) ?? ''
    expect(before).not.toBe('')

    // --- swap ----------------------------------------------------------------
    // The swap excludes the dish it replaces and keeps the row, so the one thing
    // that must change is the name in this same row.
    await row.getByRole('button', { name: 'Swap' }).click()
    await expect(dish).not.toHaveText(before)
    await expect(page.getByRole('alert')).toHaveCount(0)

    // --- lock ----------------------------------------------------------------
    await row.getByRole('button', { name: 'Lock' }).click()
    await expect(row.getByText('Locked', { exact: true })).toBeVisible()
    await expect(row.getByRole('button', { name: 'Swap' })).toBeDisabled()
    const locked = (await dish.textContent()) ?? ''

    // --- regenerate around it -----------------------------------------------
    // The hook invalidates rather than reading the mutation's body, so the plan
    // on screen is the refetched one. Wait for that GET, not just the POST, or
    // the assertion below would be reading the plan from before the click.
    const refetched = page.waitForResponse(
      (response) =>
        response.request().method() === 'GET' && response.url().includes('/plan/week?'),
    )
    await page.getByRole('button', { name: /regenerate week/i }).click()
    await refetched

    await expect(dish).toHaveText(locked)
    await expect(row.getByText('Locked', { exact: true })).toBeVisible()

    // --- unlock, so the next run's regenerate starts from a free week --------
    await row.getByRole('button', { name: 'Unlock' }).click()
    await expect(row.getByText('Locked', { exact: true })).toBeHidden()
    await expect(row.getByRole('button', { name: 'Swap' })).toBeEnabled()
  })

  test('a weigh-in lands in the list and becomes the profile weight', async ({ page }) => {
    await page.goto('/weight')
    await expect(page.getByRole('heading', { name: 'Where you are' })).toBeVisible()
    await expect(page.getByRole('note')).toHaveCount(0)

    // Onboarding recorded the first weigh-in, from the profile's 65 kg.
    await expect(page.getByRole('cell', { name: '65 kg' })).toBeVisible()

    await page.getByLabel(/weight in kg/i).fill('64.5')
    await page.getByRole('button', { name: 'Save', exact: true }).click()

    // Same day, so it replaces the onboarding weigh-in rather than joining it.
    await expect(page.getByRole('cell', { name: '64.5 kg' })).toBeVisible()
    await expect(page.getByRole('cell', { name: '65 kg' })).toHaveCount(0)

    await page.goto('/profile')
    await expect(page.getByText('64.5 kg')).toBeVisible()
  })

  test('cycle tracking is offered to a woman who menstruates, and heavy bleeding refers', async ({
    page,
  }) => {
    await page.goto('/cycle')
    // The walk onboarded a man.
    await expect(page.getByText(/cycle tracking is for profiles set to female/i)).toBeVisible()

    // Switch the profile through the real API: the wizard itself is walked above.
    const api = 'http://localhost:8000'
    const profile = await (await page.request.get(`${api}/profile`)).json()
    const saved = await page.request.put(`${api}/profile`, {
      data: { ...profile, sex: 'female', weight_kg: 55, menstrual_status: 'menstruating' },
    })
    expect(saved.ok()).toBe(true)

    await page.reload()
    const toggle = page.getByRole('switch', { name: /track my cycle/i })
    await expect(toggle).not.toBeChecked()
    // The switch shows the server's state and turns on only once the PATCH and the
    // refetch land, so check()'s one-time state read would throw. Click, then wait.
    await toggle.click()
    await expect(toggle).toBeChecked()
    await expect(page.getByText(/iron target does not change/i)).toBeVisible()
    await expect(page.getByRole('note')).toHaveCount(0)

    // Exact: the flooding question's label also contains "bleeding".
    await page.getByLabel('Bleeding', { exact: true }).selectOption('heavy')
    await page.getByRole('checkbox', { name: 'Cramps' }).check()
    await page.getByRole('button', { name: 'Save day' }).click()
    await expect(page.getByText(/heavy flow, cramps/i)).toBeVisible()

    await page.getByRole('checkbox', { name: /soak through a pad/i }).check()
    await page.getByRole('button', { name: 'Save answers' }).click()
    await expect(page.getByRole('alert')).toContainText(/please see a clinician/i)
  })

  test('the report opens on the last complete week and steps between weeks', async ({ page }) => {
    await page.goto('/report')

    // The e2e user was reset at the start of the run, so last week has nothing in it:
    // the report says so rather than drawing a week of zeros.
    const range = page.getByRole('heading', { level: 2 })
    await expect(range).toBeVisible()
    const lastWeek = (await range.textContent()) ?? ''
    await expect(page.getByText('Nothing was logged this week')).toBeVisible()
    await expect(page.getByRole('note')).toHaveCount(0)

    // Back one week, and forward again to where it started.
    await page.getByRole('button', { name: 'Previous week' }).click()
    await expect(range).not.toHaveText(lastWeek)
    await page.getByRole('button', { name: 'Next week' }).click()
    await expect(range).toHaveText(lastWeek)

    // Forward once more is the week in progress, and no further.
    await page.getByRole('button', { name: 'Next week' }).click()
    await expect(page.getByText('In progress')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Next week' })).toBeDisabled()
    await expect(page.getByRole('alert')).toHaveCount(0)
  })

  test('a meal reminder can be switched off, and stays off', async ({ page }) => {
    await page.goto('/reminders')
    await expect(page.getByRole('note')).toHaveCount(0)

    // The dev server registers no service worker, so this page cannot subscribe the
    // browser -- but the per-slot settings are the real API either way.
    const dinner = page.getByRole('switch', { name: /dinner · 20:30/i })
    await expect(dinner).toBeChecked()

    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === 'PATCH' && response.url().includes('/settings/reminders'),
    )
    await dinner.click()
    expect((await saved).ok()).toBe(true)
    await expect(dinner).not.toBeChecked()

    // A reload reads it back from the server, not from this page's cache.
    await page.reload()
    await expect(page.getByRole('switch', { name: /dinner · 20:30/i })).not.toBeChecked()

    // The mid-morning snack reminds nobody by default.
    await expect(page.getByRole('switch', { name: /mid-morning snack|snack 1/i })).not.toBeChecked()
  })
})
