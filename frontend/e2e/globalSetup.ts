import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// The package is ESM, so `__dirname` does not exist here.
const HERE = dirname(fileURLToPath(import.meta.url))
const BACKEND_DIR = resolve(HERE, '../../backend')
const STATE_PATH = resolve(HERE, '.auth/state.json')

interface Session {
  token: string
  cookie_name: string
  user_id: string
}

/**
 * Put a real session in the browser's cookie jar before any spec runs.
 *
 * `--reset` clears this one user's profile and diary rows, so the walk always
 * starts at onboarding rather than depending on what a previous run left behind.
 * The script scopes every delete to that user's id.
 */
export default function globalSetup(): void {
  const output = execFileSync('uv', ['run', 'python', '-m', 'scripts.e2e_session', '--reset'], {
    cwd: BACKEND_DIR,
    encoding: 'utf8',
  })

  const session = JSON.parse(output.trim().split('\n').pop() ?? '{}') as Session
  if (!session.token) {
    throw new Error(`Could not mint an end-to-end session. Script said:\n${output}`)
  }

  mkdirSync(dirname(STATE_PATH), { recursive: true })
  writeFileSync(
    STATE_PATH,
    JSON.stringify({
      cookies: [
        {
          name: session.cookie_name,
          value: session.token,
          // The cookie belongs to the API's origin, which is where
          // `credentials: 'include'` sends it from. localhost:5173 and
          // localhost:8000 are same-site — ports do not affect SameSite — so Lax
          // is enough and no Secure flag is needed over plain http.
          domain: 'localhost',
          path: '/',
          expires: -1,
          httpOnly: true,
          secure: false,
          sameSite: 'Lax',
        },
      ],
      origins: [],
    }),
  )
}
