import { execSync } from 'node:child_process'
import { readFileSync, rmSync } from 'node:fs'
import path from 'node:path'

const STATE_FILE = path.join(process.cwd(), 'e2e', '.state.json')

function pids(): number[] {
  try {
    const state = JSON.parse(readFileSync(STATE_FILE, 'utf-8')) as {
      backendPid?: number
      mockPid?: number
    }
    return [state.backendPid, state.mockPid].filter((pid): pid is number => typeof pid === 'number')
  } catch {
    return []
  }
}

export default async function teardown() {
  let dataDir: string | undefined
  try {
    dataDir = (JSON.parse(readFileSync(STATE_FILE, 'utf-8')) as { dataDir?: string }).dataDir
  } catch {
    return
  }
  for (const pid of pids()) {
    try {
      execSync(`kill -TERM -${pid}`, { stdio: 'ignore' })
    } catch {
      /* already gone */
    }
  }
  await new Promise((resolve) => setTimeout(resolve, 800))
  for (const pid of pids()) {
    try {
      execSync(`kill -KILL -${pid}`, { stdio: 'ignore' })
    } catch {
      /* already gone */
    }
  }
  if (dataDir) rmSync(dataDir, { recursive: true, force: true })
  rmSync(STATE_FILE, { force: true })
}
