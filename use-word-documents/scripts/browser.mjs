import fs from 'node:fs';
import path from 'node:path';
import {randomBytes, randomUUID, createHash, X509Certificate} from 'node:crypto';
import {chromium} from 'playwright';
import selfsigned from 'selfsigned';
import {STATE, accountDir, privateDir, writeJSON, loadAccount, fail, checkAccount, sleep} from './core.mjs';

export async function initialize(alias, port, root = STATE) {
  if (!Number.isInteger(port) || port < 1024 || port > 65535) fail('invalid_port', 'Choose an unused local port from 1024 through 65535.');
  privateDir(root);
  const dir = accountDir(alias, root);
  if (fs.existsSync(dir)) fail('already_initialized', 'This account state already exists. It will not be overwritten or imported.');
  fs.mkdirSync(dir, {mode: 0o700});
  const owner = randomUUID();
  privateDir(path.join(dir, 'browser'));
  privateDir(path.join(dir, 'plans'));
  const certificate = await selfsigned.generate([{name: 'commonName', value: 'localhost'}], {
    keySize: 2048, algorithm: 'sha256', notAfterDate: new Date(Date.now() + 365 * 24 * 60 * 60 * 1000),
    extensions: [{name: 'basicConstraints', cA: false}, {name: 'keyUsage', digitalSignature: true, keyEncipherment: true}, {name: 'extKeyUsage', serverAuth: true}, {name: 'subjectAltName', altNames: [{type: 2, value: 'localhost'}, {type: 7, ip: '127.0.0.1'}]}]
  });
  fs.writeFileSync(path.join(dir, 'key.pem'), certificate.private, {flag: 'wx', mode: 0o600});
  fs.writeFileSync(path.join(dir, 'cert.pem'), certificate.cert, {flag: 'wx', mode: 0o600});
  writeJSON(path.join(dir, 'browser/agent-hands-owner.json'), {owner}, true);
  writeJSON(path.join(dir, 'account.json'), {kind: 'agent-hands-word-v1', alias, owner, port, secret: randomBytes(24).toString('hex'), addinId: randomUUID()}, true);
  return loadAccount(alias, root);
}
export function launchOptions(account, headless = true) {
  const certificate = new X509Certificate(fs.readFileSync(path.join(account.dir, 'cert.pem')));
  if (Date.parse(certificate.validTo) <= Date.now()) fail('certificate_expired', 'The local bridge certificate has expired; renew it through Microsoft setup before using this profile.');
  const spki = createHash('sha256').update(certificate.publicKey.export({type: 'spki', format: 'der'})).digest('base64');
  // Persistent real-account sessions must keep Chrome's sandbox and native credential protection instead of Playwright's test defaults.
  return {headless, channel: 'chrome', chromiumSandbox: true, ignoreDefaultArgs: ['--use-mock-keychain', '--password-store=basic'], args: [`--ignore-certificate-errors-spki-list=${spki}`], acceptDownloads: false};
}
export async function launchOwnedBrowser(account, headless = true, bridge) {
  // The caller holds this account's lock. There is deliberately no arbitrary profile, CDP, executable or browser-argument option.
  const context = await chromium.launchPersistentContext(account.browserDir, launchOptions(account, headless));
  try {
    if (bridge) await context.addInitScript(({origin, prefix, token}) => {
      if (location.origin === origin && location.pathname.startsWith(prefix)) Object.defineProperty(window, 'agentHandsRunToken', {value: token});
    }, {origin: bridge.origin, prefix: bridge.prefix, token: bridge.token});
    return context;
  } catch (error) { await context.close(); throw error; }
}
export async function openBrowser(account, target, headless = true, bridge) {
  const context = await launchOwnedBrowser(account, headless, bridge);
  try {
    await context.grantPermissions(['local-network-access'], {origin: target.origin});
    const page = await context.newPage();
    for (const existing of context.pages()) if (existing !== page) await existing.close();
    const allowedOrigins = new Set([target.origin]);
    const grant = async frame => {
      try {
        const url = new URL(frame.url());
        if (url.protocol === 'https:' && url.hostname.endsWith('.officeapps.live.com') && !allowedOrigins.has(url.origin)) {
          allowedOrigins.add(url.origin);
          await context.grantPermissions(['local-network-access'], {origin: url.origin});
        }
      } catch { /* Non-HTTP frames do not receive a permission grant. */ }
    };
    page.on('framenavigated', frame => { void grant(frame); });
    await page.goto(target.webUrl, {waitUntil: 'domcontentloaded', timeout: 60_000});
    return {context, page};
  } catch (error) { await context.close(); throw error; }
}
export async function browserIdentity(context, target, profile, interactive = false) {
  const deadline = Date.now() + (interactive ? 600_000 : 15_000);
  do {
    try {
      const response = await context.request.get(target.identityUrl, {headers: {Accept: 'application/json;odata=nometadata'}, maxRedirects: 0, timeout: 10_000});
      if (response.ok()) {
        const value = await response.json();
        checkAccount(profile, value.d || value);
        return;
      }
    } catch (error) { if (error.code === 'account_mismatch') throw error; }
    await sleep(1500);
  } while (Date.now() < deadline);
  fail('authentication_required', 'The private Word browser has no verified account session. Complete normal sign-in/MFA using the Microsoft word-browser setup command; existing Chrome tabs are unaffected.');
}
