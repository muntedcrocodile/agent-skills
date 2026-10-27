import { afterEach, expect, test } from 'bun:test';
import { chmod, cp, mkdtemp, mkdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { parseEnv } from 'node:util';

const directories: string[] = [];
afterEach(async () => {
  await Promise.all(directories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});
async function fixture() {
  const root = await mkdtemp(join(tmpdir(), 'web-design-test-'));
  directories.push(root);
  const infra = join(root, 'infra/convex');
  await cp(new URL('../assets/convex-self-hosted/', import.meta.url), infra, { recursive: true });
  return { root, infra, env: join(infra, '.env') };
}
async function run(cwd: string, args: string[], env: Record<string, string | undefined> = {}) {
  const child = Bun.spawn([process.execPath, ...args], {
    cwd, env: { ...process.env, ...env }, stdout: 'pipe', stderr: 'pipe',
  });
  const [stdout, stderr, code] = await Promise.all([
    new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited,
  ]);
  return { stdout, stderr, code };
}
test('configuration is private, stable across reruns, and preserves custom settings', async () => {
  const { root, env } = await fixture();
  const first = await run(root, ['infra/convex/configure.ts']);
  expect(first.code).toBe(0);
  const original = await readFile(env, 'utf8');
  const values = parseEnv(original);
  expect(values.INSTANCE_SECRET).toMatch(/^[a-f0-9]{64}$/);
  expect((await stat(env)).mode & 0o777).toBe(0o600);
  expect(first.stdout).not.toContain(values.INSTANCE_SECRET!);
  const customised = original.replace('API_PORT=3210', 'API_PORT=43210') + '\nCUSTOM_SETTING=retained\n';
  await writeFile(env, customised);
  const second = await run(root, ['infra/convex/configure.ts']);
  expect(second.code).toBe(0);
  expect(await readFile(env, 'utf8')).toBe(customised);
});
test('an incomplete identity is rejected without modifying the file', async () => {
  const { root, env } = await fixture();
  const original = 'INSTANCE_NAME=existing-instance\nINSTANCE_SECRET=\n';
  await writeFile(env, original);
  const result = await run(root, ['infra/convex/configure.ts']);
  expect(result.code).not.toBe(0);
  expect(result.stderr).toContain('Incomplete instance identity');
  expect(await readFile(env, 'utf8')).toBe(original);
});
test('colliding ports fail validation without rewriting the environment', async () => {
  const { root, infra, env } = await fixture();
  const invalid = (await readFile(join(infra, '.env.example'), 'utf8')).replace('HTTP_PORT=3211', 'HTTP_PORT=3210');
  await writeFile(env, invalid);
  expect((await run(root, ['infra/convex/configure.ts'])).code).not.toBe(0);
  expect(await readFile(env, 'utf8')).toBe(invalid);
});
test('CLI uses private self-hosted selection, ignores stale Cloud environment, and cleans up', async () => {
  const { root } = await fixture();
  expect((await run(root, ['infra/convex/configure.ts'])).code).toBe(0);
  await mkdir(join(root, 'bin'));
  const docker = join(root, 'bin/docker');
  await writeFile(docker, '#!/usr/bin/env bash\nprintf "%s\\n" "fixture-admin-key"\n');
  await chmod(docker, 0o755);
  const module = join(root, 'node_modules/convex');
  await mkdir(join(module, 'bin'), { recursive: true });
  await writeFile(join(module, 'package.json'), JSON.stringify({ name: 'convex', type: 'module' }));
  await writeFile(join(module, 'bin/main.js'), `
import { readFileSync, statSync, writeFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
const args = process.argv.slice(2);
const selection = args[args.indexOf('--env-file') + 1];
writeFileSync('captured.json', JSON.stringify({
  args, selection, values: parseEnv(readFileSync(selection, 'utf8')),
  permissions: statSync(selection).mode & 0o777,
  staleCloud: process.env.CONVEX_DEPLOYMENT ?? null,
  staleKey: process.env.CONVEX_DEPLOY_KEY ?? null,
}));
`);
  await writeFile(join(root, '.env.local'), 'CONVEX_DEPLOYMENT=dev:unrelated-cloud\n');
  const result = await run(root, ['infra/convex/cli.ts', 'deploy', '--yes'], {
    PATH: `${join(root, 'bin')}:${process.env.PATH}`,
    CONVEX_DEPLOYMENT: 'dev:unrelated-cloud', CONVEX_DEPLOY_KEY: 'fixture-cloud-key',
  });
  expect(result.code).toBe(0);
  expect(result.stdout + result.stderr).not.toContain('fixture-admin-key');
  const captured = JSON.parse(await readFile(join(root, 'captured.json'), 'utf8'));
  expect(captured.values.CONVEX_SELF_HOSTED_ADMIN_KEY).toBe('fixture-admin-key');
  expect(captured.values.CONVEX_SELF_HOSTED_URL).toBe('http://127.0.0.1:3210');
  expect(captured.permissions).toBe(0o600);
  expect(captured.staleCloud).toBeNull();
  expect(captured.staleKey).toBeNull();
  expect(await Bun.file(captured.selection).exists()).toBe(false);
  expect(await readFile(join(root, '.env.local'), 'utf8')).toBe('CONVEX_DEPLOYMENT=dev:unrelated-cloud\n');
});
test('CLI refuses deployment-selection overrides before touching Docker', async () => {
  const { root } = await fixture();
  const result = await run(root, ['infra/convex/cli.ts', 'deploy', '--url=https://elsewhere.invalid']);
  expect(result.code).not.toBe(0);
  expect(result.stderr).toContain('Deployment selection is owned');
});
