#!/usr/bin/env node
// check-bundle-budget — deterministic gzip budget check for a built SPA.
//
// Canonical: scripts/check-bundle-budget.mjs (plan 59 Phase 5). Product repos
// carry a byte-identical vendored copy; edit this canonical and run
// scripts/sync-bundle-budget.sh — never edit the vendored copy in-repo.
// Drift is detected by the sync script and verify-wiring.sh, so this runtime
// deliberately has no --check mode.
//
// Config (default: bundle-budget.json in the current directory):
//   {
//     "distDir": "dist",
//     "entryBudgetKb": 300,
//     "initialJsBudgetKb": 900,
//     "requiredChunks": ["HomePage", "LibraryPage"]
//   }
// distDir is resolved relative to the config file. requiredChunks are
// chunk-name prefixes, never paths. v1 has no CSS or indexHtml setting.
//
// Usage:
//   node scripts/check-bundle-budget.mjs
//   node scripts/check-bundle-budget.mjs --config frontend/bundle-budget.json
//   node scripts/check-bundle-budget.mjs --self-test
//
// Exit codes: 0 ok, 1 budget/config/build failure, 2 usage.

import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { gzipSync } from 'node:zlib';

const KB = 1024;
const DEFAULT_CONFIG = 'bundle-budget.json';
const CONFIG_KEYS = new Set(['distDir', 'entryBudgetKb', 'initialJsBudgetKb', 'requiredChunks']);
const RETIRED_KEYS = new Map([
  ['includeCss', 'v1 budgets JavaScript only'],
  ['indexHtml', 'v1 reads index.html from distDir'],
]);

class CheckError extends Error {
  constructor(message) {
    super(message);
    this.name = 'CheckError';
  }
}

function parseArgs(argv) {
  const options = { configPath: DEFAULT_CONFIG, selfTest: false, help: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--self-test') {
      options.selfTest = true;
      continue;
    }
    if (arg === '--help' || arg === '-h') {
      options.help = true;
      continue;
    }
    if (arg === '--config') {
      const value = argv[index + 1];
      if (!value || value.startsWith('--')) {
        throw new CheckError('--config needs a path');
      }
      options.configPath = value;
      index += 1;
      continue;
    }
    if (arg === '--check') {
      throw new CheckError(
        '--check is not a mode of this script; run sync-bundle-budget.sh --check (or verify-wiring.sh) instead',
      );
    }
    throw new CheckError(`unknown argument: ${arg}`);
  }
  return options;
}

function readJson(path) {
  let text;
  try {
    text = readFileSync(path, 'utf8');
  } catch (error) {
    throw new CheckError(`cannot read config ${path}: ${error.message}`);
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new CheckError(`malformed config ${path}: ${error.message}`);
  }
}

function requireBudget(config, key) {
  const value = config[key];
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    throw new CheckError(`${key} must be a positive number (kB)`);
  }
  return value;
}

function validateConfig(raw, path) {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new CheckError(`malformed config ${path}: expected a JSON object`);
  }
  const unknown = Object.keys(raw).filter((key) => !CONFIG_KEYS.has(key));
  if (unknown.length > 0) {
    const retired = unknown.filter((key) => RETIRED_KEYS.has(key));
    if (retired.length > 0) {
      const detail = retired.map((key) => `${key} (${RETIRED_KEYS.get(key)})`).join(', ');
      throw new CheckError(`unsupported config key(s): ${detail}`);
    }
    throw new CheckError(`unknown config key(s): ${unknown.join(', ')}`);
  }
  if (typeof raw.distDir !== 'string' || raw.distDir.trim() === '') {
    throw new CheckError('distDir must be a non-empty string');
  }
  if (isAbsolute(raw.distDir)) {
    throw new CheckError('distDir must be relative to the config file');
  }
  const entryBudgetKb = requireBudget(raw, 'entryBudgetKb');
  const initialJsBudgetKb = requireBudget(raw, 'initialJsBudgetKb');
  if (!Array.isArray(raw.requiredChunks)) {
    throw new CheckError('requiredChunks must be an array of chunk-name prefixes');
  }
  const seen = new Set();
  const requiredChunks = raw.requiredChunks.map((chunk) => {
    if (typeof chunk !== 'string' || chunk.trim() === '') {
      throw new CheckError('requiredChunks entries must be non-empty strings');
    }
    if (/[/\\]/.test(chunk) || chunk.endsWith('.js')) {
      throw new CheckError(`requiredChunks entry "${chunk}" must be a chunk-name prefix, not a path or filename`);
    }
    if (seen.has(chunk)) {
      throw new CheckError(`duplicate requiredChunks entry: ${chunk}`);
    }
    seen.add(chunk);
    return chunk;
  });
  return {
    configPath: path,
    distDir: resolve(dirname(path), raw.distDir),
    entryBudgetKb,
    initialJsBudgetKb,
    requiredChunks,
  };
}

function loadConfig(configPath) {
  const path = resolve(configPath);
  return validateConfig(readJson(path), path);
}

function parseAttributes(tag) {
  const attributes = new Map();
  const tagName = tag.slice(1).trimStart().split(/[\s/>]/, 1)[0].toLowerCase();
  const pattern = /([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  let match = pattern.exec(tag);
  while (match !== null) {
    const name = match[1].toLowerCase();
    if (name !== tagName) {
      attributes.set(name, match[2] ?? match[3] ?? match[4] ?? '');
    }
    match = pattern.exec(tag);
  }
  return attributes;
}

function moduleAssets(html) {
  const entry = [];
  const preloads = [];
  for (const match of html.matchAll(/<(script|link)\b[^>]*>/gi)) {
    const tag = match[0];
    const name = match[1].toLowerCase();
    const attributes = parseAttributes(tag);
    if (name === 'script') {
      if ((attributes.get('type') ?? '').toLowerCase() !== 'module') continue;
      const src = attributes.get('src');
      if (src) entry.push(src);
      continue;
    }
    const rel = (attributes.get('rel') ?? '').toLowerCase().split(/\s+/);
    const href = attributes.get('href');
    if (href && rel.includes('modulepreload') && /\.m?js(?:[?#]|$)/i.test(href)) {
      preloads.push(href);
    }
  }
  return { entry, preloads };
}

function assetFile(distDir, url) {
  const clean = url.split(/[?#]/, 1)[0];
  if (clean === '') {
    throw new CheckError(`empty asset URL: ${url}`);
  }
  if (/^[a-z][a-z0-9+.-]*:/i.test(clean) || clean.startsWith('//')) {
    throw new CheckError(`external asset URL is not supported: ${url}`);
  }
  const path = resolve(distDir, clean.replace(/^\/+/, ''));
  const inside = relative(distDir, path);
  if (inside === '' || inside === '..' || inside.startsWith(`..${sep}`) || isAbsolute(inside)) {
    throw new CheckError(`asset resolves outside distDir: ${url}`);
  }
  if (!existsSync(path) || !statSync(path).isFile()) {
    throw new CheckError(`asset is missing: ${url}`);
  }
  return path;
}

function gzipBytes(path) {
  return gzipSync(readFileSync(path), { level: 9 }).length;
}

function walkFiles(dir) {
  const files = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkFiles(path));
    } else if (entry.isFile()) {
      files.push(path);
    }
  }
  return files;
}

function formatKb(bytes) {
  return `${(bytes / KB).toFixed(1)} kB`;
}

function runCheck(configPath) {
  const config = loadConfig(configPath);
  const indexPath = join(config.distDir, 'index.html');
  if (!existsSync(indexPath)) {
    throw new CheckError(
      `dist/index.html missing at ${indexPath} — run the app build before check-bundle-budget`,
    );
  }
  const html = readFileSync(indexPath, 'utf8');
  const { entry, preloads } = moduleAssets(html);
  if (entry.length === 0) {
    throw new CheckError('no external <script type="module"> entry found in dist/index.html');
  }
  if (entry.length > 1) {
    throw new CheckError(`expected one module entry, found ${entry.length}: ${entry.join(', ')}`);
  }

  const entryPath = assetFile(config.distDir, entry[0]);
  const preloadPaths = [...new Set(preloads.map((url) => assetFile(config.distDir, url)))];
  const initialPaths = [...new Set([entryPath, ...preloadPaths])];
  const entryBytes = gzipBytes(entryPath);
  const initialBytes = initialPaths.reduce((total, path) => total + gzipBytes(path), 0);
  const preloadCount = initialPaths.length - 1;

  const chunkFiles = walkFiles(config.distDir)
    .map((path) => basename(path))
    .filter((name) => name.endsWith('.js'));
  const missingChunks = config.requiredChunks.filter(
    (prefix) => !chunkFiles.some((name) => name.startsWith(prefix)),
  );

  const problems = [];
  if (entryBytes > config.entryBudgetKb * KB) {
    problems.push(
      `entry JS is over budget: ${formatKb(entryBytes)} > ${formatKb(config.entryBudgetKb * KB)}`,
    );
  }
  if (initialBytes > config.initialJsBudgetKb * KB) {
    problems.push(
      `initial JS is over budget: ${formatKb(initialBytes)} > ${formatKb(config.initialJsBudgetKb * KB)}`,
    );
  }
  if (missingChunks.length > 0) {
    problems.push(`missing required route chunk(s): ${missingChunks.join(', ')}`);
  }

  return {
    ok: problems.length === 0,
    problems,
    config,
    lines: [
      `config: ${config.configPath}`,
      `dist: ${config.distDir}`,
      `entry JS: ${formatKb(entryBytes)} (budget ${formatKb(config.entryBudgetKb * KB)})`,
      `initial JS: ${formatKb(initialBytes)} incl. ${preloadCount} modulepreload(s) ` +
        `(budget ${formatKb(config.initialJsBudgetKb * KB)})`,
      `required chunks: ${config.requiredChunks.length - missingChunks.length}/${config.requiredChunks.length} present`,
    ],
  };
}

function pseudoRandomBytes(size, seed) {
  const buffer = Buffer.allocUnsafe(size);
  let state = seed >>> 0 || 1;
  for (let index = 0; index < size; index += 1) {
    state ^= state << 13;
    state >>>= 0;
    state ^= state >>> 17;
    state ^= state << 5;
    state >>>= 0;
    buffer[index] = state & 0xff;
  }
  return buffer;
}

function writeFixture(root, options) {
  const dist = join(root, 'dist');
  const assets = join(dist, 'assets');
  mkdirSync(assets, { recursive: true });
  const entryName = options.entryName ?? 'index-fixture.js';
  const preloads = options.preloads ?? [];
  writeFileSync(join(dist, entryName), pseudoRandomBytes(options.entryBytes ?? 40 * KB, 1));
  for (const [index, preload] of preloads.entries()) {
    writeFileSync(join(dist, preload.name), pseudoRandomBytes(preload.bytes, index + 2));
  }
  for (const [index, chunk] of (options.chunks ?? []).entries()) {
    writeFileSync(join(assets, chunk), pseudoRandomBytes(1024, index + 10));
  }
  const scripts = `<script type="module" crossorigin src="/${entryName}"></script>`;
  const links = preloads
    .map((preload) => `<link rel="modulepreload" crossorigin href="/${preload.name}">`)
    .join('\n    ');
  writeFileSync(
    join(dist, 'index.html'),
    options.html ?? `<!doctype html>\n<html><head>\n    ${links}\n  </head>\n  <body>${scripts}</body></html>\n`,
  );
  return dist;
}

function writeConfig(root, values, name = 'bundle-budget.json') {
  const path = join(root, name);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(values, null, 2)}\n`);
  return path;
}

function selfTest() {
  const root = mkdtempSync(join(tmpdir(), 'bundle-budget-'));
  const cases = [];
  const register = (name, fn) => cases.push({ name, fn });
  const expectOk = (name, configPath) => {
    register(name, () => {
      const result = runCheck(configPath);
      if (!result.ok) {
        throw new Error(`expected ok, got: ${result.problems.join('; ')}`);
      }
    });
  };
  const expectProblem = (name, configPath, needle) => {
    register(name, () => {
      const result = runCheck(configPath);
      if (result.ok) throw new Error('expected a budget failure, got ok');
      if (!result.problems.some((problem) => problem.includes(needle))) {
        throw new Error(`expected a problem containing "${needle}", got: ${result.problems.join('; ')}`);
      }
    });
  };
  const expectThrow = (name, fn, needle) => {
    register(name, () => {
      try {
        fn();
      } catch (error) {
        if (!(error instanceof CheckError)) throw error;
        if (!error.message.includes(needle)) {
          throw new Error(`expected "${needle}", got: ${error.message}`);
        }
        return;
      }
      throw new Error('expected a check error, got success');
    });
  };

  try {
    const good = join(root, 'good');
    writeFixture(good, {
      entryBytes: 40 * KB,
      preloads: [
        { name: 'vendor-fixture.js', bytes: 30 * KB },
        { name: 'runtime-fixture.js', bytes: 20 * KB },
      ],
      chunks: ['HomePage-fixture.js', 'LibraryPage-fixture.js'],
    });
    const goodConfig = writeConfig(good, {
      distDir: 'dist',
      entryBudgetKb: 100,
      initialJsBudgetKb: 200,
      requiredChunks: ['HomePage', 'LibraryPage'],
    });
    expectOk('valid tree passes', goodConfig);

    const entryPreload = join(root, 'entry-preload');
    writeFixture(entryPreload, {
      entryBytes: 40 * KB,
      preloads: [{ name: 'index-fixture.js', bytes: 40 * KB }],
      chunks: ['HomePage-fixture.js'],
    });
    expectOk(
      'entry is not double-counted when modulepreloaded',
      writeConfig(entryPreload, {
        distDir: 'dist',
        entryBudgetKb: 100,
        initialJsBudgetKb: 60,
        requiredChunks: ['HomePage'],
      }),
    );

    const prefix = join(root, 'prefix');
    writeFixture(prefix, {
      entryBytes: 40 * KB,
      chunks: ['HomePageOld-fixture.js'],
    });
    expectOk(
      'required chunk prefix matches HomePageOld',
      writeConfig(prefix, {
        distDir: 'dist',
        entryBudgetKb: 100,
        initialJsBudgetKb: 200,
        requiredChunks: ['HomePage'],
      }),
    );

    const entryOver = join(root, 'entry-over');
    writeFixture(entryOver, {
      entryBytes: 40 * KB,
      chunks: ['HomePage-fixture.js'],
    });
    expectProblem(
      'entry over budget fails',
      writeConfig(entryOver, {
        distDir: 'dist',
        entryBudgetKb: 20,
        initialJsBudgetKb: 200,
        requiredChunks: ['HomePage'],
      }),
      'entry JS is over budget',
    );

    const initialOver = join(root, 'initial-over');
    writeFixture(initialOver, {
      entryBytes: 40 * KB,
      preloads: [
        { name: 'vendor-fixture.js', bytes: 40 * KB },
        { name: 'runtime-fixture.js', bytes: 40 * KB },
      ],
      chunks: ['HomePage-fixture.js'],
    });
    expectProblem(
      'initial JS over budget fails',
      writeConfig(initialOver, {
        distDir: 'dist',
        entryBudgetKb: 100,
        initialJsBudgetKb: 100,
        requiredChunks: ['HomePage'],
      }),
      'initial JS is over budget',
    );

    const missingChunk = join(root, 'missing-chunk');
    writeFixture(missingChunk, {
      entryBytes: 40 * KB,
      chunks: ['HomePage-fixture.js'],
    });
    expectProblem(
      'missing required chunk fails',
      writeConfig(missingChunk, {
        distDir: 'dist',
        entryBudgetKb: 100,
        initialJsBudgetKb: 200,
        requiredChunks: ['HomePage', 'SettingsPage'],
      }),
      'SettingsPage',
    );

    const nested = join(root, 'nested');
    writeFixture(join(nested, 'app'), {
      entryBytes: 40 * KB,
      chunks: ['HomePage-fixture.js'],
    });
    const nestedConfig = writeConfig(join(nested, 'app'), {
      distDir: 'dist',
      entryBudgetKb: 100,
      initialJsBudgetKb: 200,
      requiredChunks: ['HomePage'],
    });
    expectOk('distDir resolves relative to the config file', nestedConfig);

    expectThrow(
      'malformed JSON fails',
      () => {
        const path = join(root, 'bad.json');
        writeFileSync(path, '{');
        runCheck(path);
      },
      'malformed config',
    );
    expectThrow(
      'missing dist fails',
      () =>
        runCheck(
          writeConfig(join(root, 'no-dist'), {
            distDir: 'dist',
            entryBudgetKb: 100,
            initialJsBudgetKb: 200,
            requiredChunks: [],
          }),
        ),
      'dist/index.html missing',
    );
    expectThrow(
      'unknown config key fails',
      () =>
        runCheck(
          writeConfig(join(root, 'unknown-key'), {
            distDir: 'dist',
            entryBudgetKb: 100,
            initialJsBudgetKb: 200,
            requiredChunks: [],
            budgetKb: 1,
          }),
        ),
      'unknown config key',
    );
    expectThrow(
      'retired includeCss fails',
      () =>
        runCheck(
          writeConfig(join(root, 'include-css'), {
            distDir: 'dist',
            entryBudgetKb: 100,
            initialJsBudgetKb: 200,
            requiredChunks: [],
            includeCss: true,
          }),
        ),
      'includeCss',
    );
    expectThrow(
      'chunk path is rejected',
      () =>
        runCheck(
          writeConfig(join(root, 'chunk-path'), {
            distDir: 'dist',
            entryBudgetKb: 100,
            initialJsBudgetKb: 200,
            requiredChunks: ['assets/HomePage'],
          }),
        ),
      'chunk-name prefix',
    );
    expectThrow(
      'absolute distDir is rejected',
      () =>
        runCheck(
          writeConfig(join(root, 'absolute-dist'), {
            distDir: '/tmp/dist',
            entryBudgetKb: 100,
            initialJsBudgetKb: 200,
            requiredChunks: [],
          }),
        ),
      'relative to the config file',
    );

    const noEntry = join(root, 'no-entry');
    writeFixture(noEntry, { entryBytes: 40 * KB, html: '<!doctype html><html><body>plain</body></html>' });
    expectThrow(
      'missing module entry fails',
      () =>
        runCheck(
          writeConfig(noEntry, {
            distDir: 'dist',
            entryBudgetKb: 100,
            initialJsBudgetKb: 200,
            requiredChunks: [],
          }),
        ),
      'no external <script type="module"> entry',
    );

    const missingAsset = join(root, 'missing-asset');
    writeFixture(missingAsset, {
      entryBytes: 40 * KB,
      html: '<!doctype html><html><body><script type="module" src="/gone.js"></script></body></html>',
    });
    expectThrow(
      'missing entry asset fails',
      () =>
        runCheck(
          writeConfig(missingAsset, {
            distDir: 'dist',
            entryBudgetKb: 100,
            initialJsBudgetKb: 200,
            requiredChunks: [],
          }),
        ),
      'asset is missing',
    );

    expectThrow(
      '--check is rejected',
      () => parseArgs(['--check']),
      'sync-bundle-budget.sh',
    );
    expectThrow(
      '--config without a value is rejected',
      () => parseArgs(['--config']),
      'needs a path',
    );

    let failures = 0;
    for (const entry of cases) {
      try {
        entry.fn();
      } catch (error) {
        failures += 1;
        console.error(`  FAIL ${entry.name}: ${error.message}`);
      }
    }
    if (failures > 0) {
      console.error(`bundle-budget self-test: ${cases.length - failures}/${cases.length} passed`);
      return false;
    }
    console.log(`bundle-budget self-test: ${cases.length}/${cases.length} passed`);
    return true;
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

function usage() {
  console.log(
    'Usage: node scripts/check-bundle-budget.mjs [--config <path>] [--self-test]\n' +
      `Default config: ${DEFAULT_CONFIG} in the current directory.`,
  );
}

function main() {
  let options;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(`check-bundle-budget: ${error.message}`);
    usage();
    process.exit(2);
  }
  if (options.help) {
    usage();
    return;
  }
  if (options.selfTest) {
    process.exit(selfTest() ? 0 : 1);
  }
  try {
    const result = runCheck(options.configPath);
    for (const line of result.lines) console.log(line);
    if (result.ok) {
      console.log('check-bundle-budget: OK');
      return;
    }
    for (const problem of result.problems) console.error(`FAIL: ${problem}`);
    process.exit(1);
  } catch (error) {
    if (!(error instanceof CheckError)) throw error;
    console.error(`check-bundle-budget: ${error.message}`);
    process.exit(1);
  }
}

main();
