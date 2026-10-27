import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseEnv } from 'node:util';

// Invoke from the application root, where convex is a locked project dependency.
const args = process.argv.slice(2);
const commands = ['dev', 'deploy', 'codegen', 'run', 'env', 'export', 'import'];
if (!commands.includes(args[0] ?? '')) throw new Error(`Choose a Convex command: ${commands.join(', ')}`);
if (args.some((arg) => /^--(env-file|url|admin-key|prod|deployment-name|preview-name|preview-create|configure|local|cloud)(=|$)/.test(arg))) {
  throw new Error('Deployment selection is owned by infra/convex/.env; do not override it with CLI flags.');
}
const directory = dirname(fileURLToPath(import.meta.url));
const values = parseEnv(await readFile(join(directory, '.env'), 'utf8'));
if (!values.COMPOSE_PROJECT_NAME || !values.INSTANCE_NAME || !values.INSTANCE_SECRET) {
  throw new Error('Run configure.ts and start the backend first.');
}
const require = createRequire(resolve('package.json'));
const executable = join(dirname(require.resolve('convex/package.json')), 'bin/main.js');
const admin = Bun.spawn([
  'docker', 'compose', '--env-file', join(directory, '.env'), '-f', join(directory, 'compose.yaml'),
  'exec', '-T', 'backend', './generate_admin_key.sh',
], { stdout: 'pipe', stderr: 'pipe', env: { ...process.env, ...values } });
// Capture both streams; failures must not accidentally print credentials.
const [output] = await Promise.all([new Response(admin.stdout).text(), new Response(admin.stderr).text()]);
if (await admin.exited !== 0) throw new Error('Cannot obtain the admin key. Check that this Compose backend is healthy.');
const key = output.trim();
if (!key || /[\r\n'"\\]/.test(key)) throw new Error('Unexpected administrator key format.');
const url = values.CONVEX_CLOUD_ORIGIN ?? '';
if (!/^https?:\/\//.test(url) || /[\r\n'"\\]/.test(url)) throw new Error('Invalid API origin.');
const temporary = await mkdtemp(join(tmpdir(), 'convex-cli-'));
try {
  const selection = join(temporary, '.env');
  await writeFile(selection, `CONVEX_SELF_HOSTED_URL='${url}'\nCONVEX_SELF_HOSTED_ADMIN_KEY='${key}'\n`, { mode: 0o600 });
  // --env-file isolates selection from a stale Cloud deployment in .env.local.
  const env = { ...process.env };
  for (const name of ['CONVEX_DEPLOY_KEY', 'CONVEX_DEPLOYMENT', 'CONVEX_SELF_HOSTED_URL', 'CONVEX_SELF_HOSTED_ADMIN_KEY']) delete env[name];
  const child = Bun.spawn([process.execPath, executable, ...args, '--env-file', selection], {
    stdin: 'inherit', stdout: 'inherit', stderr: 'inherit', env,
  });
  const forward = (signal: 'SIGINT' | 'SIGTERM') => child.kill(signal);
  process.on('SIGINT', forward);
  process.on('SIGTERM', forward);
  process.exitCode = await child.exited;
  process.off('SIGINT', forward);
  process.off('SIGTERM', forward);
} finally {
  await rm(temporary, { recursive: true, force: true });
}
