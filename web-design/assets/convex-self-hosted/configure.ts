import { randomBytes } from 'node:crypto';
import { chmod, readFile, rename, writeFile } from 'node:fs/promises';
import { parseEnv } from 'node:util';

const envPath = new URL('.env', import.meta.url);
const exists = await Bun.file(envPath).exists();
let content = await readFile(exists ? envPath : new URL('.env.example', import.meta.url), 'utf8');
const values = parseEnv(content);
if (Boolean(values.INSTANCE_NAME) !== Boolean(values.INSTANCE_SECRET)) {
  throw new Error('Incomplete instance identity. Restore both values; do not rotate an existing identity.');
}
const generated: Record<string, string> = {
  COMPOSE_PROJECT_NAME: `web-${randomBytes(6).toString('hex')}`,
  INSTANCE_NAME: `web-${randomBytes(6).toString('hex')}`,
  INSTANCE_SECRET: randomBytes(32).toString('hex'),
};
for (const [key, value] of Object.entries(generated)) {
  if (values[key]) continue;
  values[key] = value;
  const pattern = new RegExp(`^${key}=.*$`, 'm');
  content = pattern.test(content)
    ? content.replace(pattern, () => `${key}=${value}`)
    : `${content}\n${key}=${value}\n`;
}
if (!/^[a-z0-9][a-z0-9_-]*$/.test(values.COMPOSE_PROJECT_NAME ?? '') ||
    !/^[a-zA-Z0-9_-]+$/.test(values.INSTANCE_NAME ?? '') ||
    !/^[a-f0-9]{64}$/.test(values.INSTANCE_SECRET ?? '')) {
  throw new Error('Invalid Compose project name or instance identity. Existing values were not changed.');
}
const ports = ['API_PORT', 'HTTP_PORT'].map((name) => Number(values[name]));
if (ports.some((port) => !Number.isInteger(port) || port < 1 || port > 65535) || ports[0] === ports[1]) {
  throw new Error('API_PORT and HTTP_PORT must be distinct ports between 1 and 65535.');
}
for (const name of ['CONVEX_CLOUD_ORIGIN', 'CONVEX_SITE_ORIGIN']) {
  const value = values[name] ?? '';
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.origin !== value) {
    throw new Error(`${name} must be an HTTP(S) origin without a path, credentials, or trailing slash.`);
  }
}
for (const name of ['CONVEX_BACKEND_IMAGE', 'NGINX_IMAGE']) {
  if (!/@sha256:[a-f0-9]{64}$/.test(values[name] ?? '')) {
    throw new Error(`${name} must be pinned by image digest.`);
  }
}
const temporary = new URL(`.env.${randomBytes(6).toString('hex')}.tmp`, import.meta.url);
await writeFile(temporary, content, { mode: 0o600, flag: 'wx' });
await rename(temporary, envPath);
await chmod(envPath, 0o600);
console.log('Convex configuration ready. Existing values preserved; secrets were not printed.');
