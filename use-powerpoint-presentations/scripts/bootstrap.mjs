import {fail, sameDocument, sleep} from './core.mjs';
import {manifest} from './bridge.mjs';

// Only the owned browser and verified document enter this setup path. Document text never supplies selectors, scripts, manifests or destinations.
export async function openAddinAutomatically(browser, bridge, account, target) {
  const page = browser.page;
  const guard = () => { if (!sameDocument(page.url(), target)) fail('target_mismatch', 'The setup page no longer identifies the selected document. No further setup action was sent.'); };
  const ready = async timeout => {
    try { await bridge.waitReady(timeout); return true; }
    catch (error) { if (error.code !== 'addin_setup_required') throw error; return false; }
  };
  guard();
  if (await ready(5000)) return 'already_running';
  await page.setViewportSize({width: 1600, height: 1000});
  let frame;
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    frame = page.frames().find(f => {
      try { const url = new URL(f.url()); return /^WacFrame_PowerPoint_\d+$/.test(f.name()) && url.protocol === 'https:' && url.hostname.endsWith('.officeapps.live.com'); } catch { return false; }
    });
    if (frame && await frame.getByRole('tab', {name: 'Home', exact: true}).isVisible()) break;
    await sleep(250);
  }
  if (!frame) fail('automatic_setup_unavailable', 'The expected PowerPoint web editor did not load. Use powerpoint-browser configure in the owned profile.');
  const click = async locator => { guard(); await locator.click({timeout: 8000}); };
  const openCommand = async () => {
    const button = frame.getByRole('button', {name: 'Open PowerPoint tools', exact: true});
    if (await button.isVisible()) { await click(button); return true; }
    const more = frame.getByRole('button', {name: 'More Options', exact: true});
    if (await more.isVisible()) {
      await click(more);
      const item = frame.getByRole('menuitem', {name: 'Open PowerPoint tools', exact: true});
      if (await item.isVisible()) { await click(item); return true; }
      await more.press('Escape');
    }
    return false;
  };
  let installed = false;
  try {
    if (!await openCommand()) {
      const addins=frame.getByRole('button', {name: 'Add-ins', exact: true});
      guard();await addins.focus();await addins.press('Enter');
      await click(frame.getByText('Advanced...', {exact: true}));
      let catalog;
      const until = Date.now() + 20_000;
      while (Date.now() < until) {
        catalog = page.frames().find(f => {
          try { return new URL(f.url()).origin === new URL(frame.url()).origin && f.name().startsWith('_xdm_') && f.parentFrame() === frame; } catch { return false; }
        });
        if (catalog && await catalog.getByText('Upload My Add-in', {exact: true}).isVisible()) break;
        await sleep(250);
      }
      if (!catalog) fail('automatic_setup_unavailable', 'The expected add-in upload dialog is unavailable. Tenant policy or the PowerPoint UI may differ; use powerpoint-browser configure in the owned profile.');
      await click(catalog.getByText('Upload My Add-in', {exact: true}));
      guard();
      await catalog.locator('input[type=file]').setInputFiles({name: 'agent-hands-powerpoint.xml', mimeType: 'text/xml', buffer: Buffer.from(manifest(account))}, {timeout: 8000});
      await click(catalog.getByRole('button', {name: 'Upload', exact: true}));
      installed = true;
      await frame.locator('[aria-label="Open PowerPoint tools"]').waitFor({state: 'attached', timeout: 20_000});
      // Refresh the ribbon layout after installation; PowerPoint can initially leave the new command hidden in overflow.
      await click(frame.getByRole('tab', {name: 'Insert', exact: true}));
      await click(frame.getByRole('tab', {name: 'Home', exact: true}));
      if (!await openCommand()) fail('automatic_setup_unavailable', 'The installed bridge command is unavailable. Use powerpoint-browser configure in the owned profile; no document content edit was sent.');
    }
    if (!await ready(30_000)) fail('automatic_setup_incomplete', 'The add-in did not connect after setup. This document may retain an add-in reference; use powerpoint-browser configure before retrying. No content edit was sent.');
    guard();
    return installed ? 'installed' : 'opened';
  } catch (error) {
    if (error.code) throw error;
    fail('automatic_setup_unavailable', 'Automatic setup could not complete using the expected English PowerPoint web controls. This document may retain an add-in reference. Use powerpoint-browser configure in the owned profile; no content edit was sent.');
  }
}

// Persisted startup can take longer than the ribbon's initial appearance. Avoid setup clicks while that known add-in is still loading.
export async function prepareAddin(browser, bridge, account, target, cloudStartup) {
  if (!cloudStartup) return openAddinAutomatically(browser, bridge, account, target);
  if (!sameDocument(browser.page.url(), target)) fail('target_mismatch', 'The prepared page no longer identifies the selected presentation.');
  try { await bridge.waitReady(90_000); }
  catch (error) {
    if (error.code !== 'addin_setup_required') throw error;
    fail('automatic_setup_incomplete', 'Cloud startup is already enabled, but its add-in did not connect. Check sign-in or use powerpoint-browser configure in the owned profile; no setup click or content edit was sent.');
  }
  return 'already_running';
}
