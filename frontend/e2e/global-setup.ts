import { spawn } from 'node:child_process'
import { mkdirSync, mkdtempSync, openSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import os from 'node:os'
import path from 'node:path'

const FRONTEND = process.cwd()
const ROOT = path.resolve(FRONTEND, '..')
const BACKEND = path.join(ROOT, 'backend')
const STATE_FILE = path.join(FRONTEND, 'e2e', '.state.json')

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

  writeFileSync(
    STATE_FILE,
    JSON.stringify({
      baseUrl,
      dataDir,
      mockBaseUrl: `http://127.0.0.1:${mockPort}/v1`,
      backendPid: backend.pid,
      mockPid: mock.pid,
    })
  )
}
