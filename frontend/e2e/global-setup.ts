import { spawn } from 'node:child_process'
import { mkdirSync, mkdtempSync, openSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import os from 'node:os'
import path from 'node:path'

const FRONTEND = process.cwd()
const ROOT = path.resolve(FRONTEND, '..')
const BACKEND = path.join(ROOT, 'backend')
const STATE_FILE = path.join(FRONTEND, 'e2e', '.state.json')
const AUTH_STATE_FILE = path.join(FRONTEND, 'e2e', '.auth-state.json')

async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.unref()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      if (address && typeof address === 'object') {
        const port = address.port
        server.close(() => resolve(port))
      } else {
        server.close(() => reject(new Error('no port')))
      }
    })
  })
}

async function waitHealthy(url: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      /* not up yet */
    }
    await new Promise((resolve) => setTimeout(resolve, 300))
  }
  throw new Error(`server never became healthy at ${url}`)
}

async function run(command: string, args: string[], cwd: string): Promise<void> {
  const child = spawn(command, args, { cwd, stdio: 'inherit' })
  await new Promise<void>((resolve, reject) => {
    child.on('exit', (code) =>
      code === 0 ? resolve() : reject(new Error(`${command} exited ${code}`))
    )
  })
}

export default async function setup() {
  const backendPort = await freePort()
  const mockPort = await freePort()
  const dataDir = mkdtempSync(path.join(os.tmpdir(), 'sa-e2e-'))
  mkdirSync(path.join(FRONTEND, 'test-results'), { recursive: true })

  await run('pnpm', ['build'], FRONTEND)

  const mockLog = openSync(path.join(FRONTEND, 'test-results', 'mock-provider.log'), 'a')
  const mock = spawn(
    'uv',
    ['run', 'python', '-m', 'uvicorn', 'mock_provider:app', '--host', '127.0.0.1', '--port', String(mockPort)],
    {
      cwd: BACKEND,
      stdio: ['ignore', mockLog, mockLog],
      detached: true,
      env: { ...process.env, PYTHONPATH: path.join(FRONTEND, 'e2e') },
    }
  )
  await waitHealthy(`http://127.0.0.1:${mockPort}/v1/models`, 30_000)

  const backendLog = openSync(path.join(FRONTEND, 'test-results', 'backend.log'), 'a')
  const backend = spawn(
    'uv',
    [
      'run',
      'python',
      path.join(FRONTEND, 'e2e', 'run_backend.py'),
      '--port',
      String(backendPort),
      '--data-dir',
      dataDir,
    ],
    { cwd: BACKEND, stdio: ['ignore', backendLog, backendLog], detached: true }
  )
  const baseUrl = `http://127.0.0.1:${backendPort}`
  await waitHealthy(`${baseUrl}/api/v1/health`, 60_000)

  // Bootstrap the e2e service session. Since S4b enforces a session on
  // every /api/* request, the suite's node helpers and the SPA's own
  // queries need a real login: register on the fresh instance (user #1,
  // admin — the instance is re-created per run so this is always new).
  // The onboarding wizard's "fresh" state is provider/course-based, not
  // user-count-based, so test 01's fresh-boot expectation is unaffected.
  const register = await fetch(`${baseUrl}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: 'e2e-runner@example.test',
      password: 'E2E-service-not-a-real-secret',
    }),
  })
  if (!register.ok) {
    throw new Error(`e2e service registration failed: ${register.status} ${await register.text()}`)
  }
  const setCookies: string[] =
    typeof register.headers.getSetCookie === 'function'
      ? register.headers.getSetCookie()
      : [register.headers.get('set-cookie') ?? ''].filter(Boolean)
  const cookies = setCookies.map((raw) => {
    const [pair, ...attrs] = raw.split(';')
    const eq = pair.indexOf('=')
    const parsed: {
      name: string
      value: string
      domain: string
      path: string
      expires: number
      httpOnly: boolean
      secure: boolean
      sameSite: 'Lax' | 'Strict' | 'None'
    } = {
      name: pair.slice(0, eq).trim(),
      value: pair.slice(eq + 1).trim(),
      domain: '127.0.0.1',
      path: '/',
      expires: -1,
      httpOnly: false,
      secure: false,
      sameSite: 'Lax',
    }
    for (const attr of attrs) {
      const [k, v] = attr.split('=')
      const key = k.trim().toLowerCase()
      if (key === 'path') parsed.path = (v ?? '/').trim()
      else if (key === 'httponly') parsed.httpOnly = true
      else if (key === 'secure') parsed.secure = true
      else if (key === 'samesite') {
        const raw = (v ?? 'Lax').trim().toLowerCase()
        parsed.sameSite = raw === 'strict' ? 'Strict' : raw === 'none' ? 'None' : 'Lax'
      }
    }
    return parsed
  })
  const csrfToken = cookies.find((c) => c.name === 'nx_csrf')?.value ?? ''
  const serviceCookie = cookies.map((c) => `${c.name}=${c.value}`).join('; ')
  // Profile binding (S5): API calls must name the profile — resolve the
  // auto-provisioned Default profile of the service account.
  const profilesRes = await fetch(`${baseUrl}/api/v1/profiles`, {
    headers: { Cookie: serviceCookie },
  })
  if (!profilesRes.ok) {
    throw new Error(`e2e profile lookup failed: ${profilesRes.status} ${await profilesRes.text()}`)
  }
  const profiles = (await profilesRes.json()) as Array<{ id: string; is_default?: boolean }>
  const profileId = (profiles.find((p) => p.is_default) ?? profiles[0])?.id ?? ''
  if (!profileId) throw new Error('e2e service account has no profile')
  // Browser contexts get the same session via storageState (cookies
  // only — origins stays empty so per-context localStorage is fresh and
  // the onboarding wizard's dismissal flag never leaks between tests).
  writeFileSync(
    AUTH_STATE_FILE,
    JSON.stringify({ cookies, origins: [] }),
  )

  writeFileSync(
    STATE_FILE,
    JSON.stringify({
      baseUrl,
      dataDir,
      mockBaseUrl: `http://127.0.0.1:${mockPort}/v1`,
      backendPid: backend.pid,
      mockPid: mock.pid,
      serviceCookie,
      csrfToken,
      profileId,
    })
  )
}
