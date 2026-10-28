import { test, expect } from '@playwright/test';

test.beforeEach(async ({ browser }, info) => {
  info.annotations.push({ type: 'browser-version', description: browser.version() });
});

test('immutable bytes, generic concatenation and captured callbacks update browser state', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'NEX binary values' })).toBeVisible();
  const value = page.getByRole('status');
  await expect(value).toHaveText('AP+AQQ==');
  await expect(page.getByLabel('Octets', { exact: true })).toHaveText('4');
  await expect(page.getByLabel('UTF-8', { exact: true })).toHaveText('E_UTF8');
  await page.getByRole('button', { name: 'Append NUL' }).click();
  await expect(value).toHaveText('AP+AQQA=');
  await expect(page.getByLabel('History')).toHaveText('["AP+AQQ==","AP+AQQA="]');
  await page.getByRole('button', { name: 'Keep last 2' }).click();
  await expect(value).toHaveText('QQA=');
  await expect(page.getByLabel('Octets', { exact: true })).toHaveText('2');
  await expect(page.getByLabel('History')).toHaveText('["AP+AQQ==","AP+AQQA=","QQA="]');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(value).toHaveText('AP+AQQ==');
  await expect(page.getByLabel('History')).toHaveText('["AP+AQQ=="]');
  await page.reload();
  await expect(value).toHaveText('AP+AQQ==');
  expect(errors).toEqual([]);
});

test('strict codecs reject invalid edits and preserve every octet', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  const value = page.getByRole('status');
  const input = page.getByLabel('Base64', { exact: true });
  const apply = page.getByRole('button', { name: 'Apply', exact: true });
  for (const source of ['AB==', 'AA', '_w==', 'AA===', 'AA== ']) {
    await input.fill(source); await apply.click();
    await expect(page.getByRole('alert')).toHaveText('E_BASE64');
    await expect(value).toHaveText('AP+AQQ==');
    await expect(page.getByLabel('History')).toHaveText('["AP+AQQ=="]');
  }
  const octets = Buffer.from(Array.from({ length: 256 }, (_, i) => i)).toString('base64');
  await input.fill(octets); await apply.click();
  await expect(value).toHaveText(octets);
  await expect(page.getByLabel('Octets', { exact: true })).toHaveText('256');
  await expect(page.getByRole('alert')).toBeEmpty();
  const unicode = '\uFEFFЯ\0🧠';
  const encoded = Buffer.from(unicode, 'utf8').toString('base64');
  await input.fill(encoded); await apply.click();
  await expect(value).toHaveText(encoded);
  expect(await page.getByLabel('UTF-8', { exact: true }).textContent()).toBe(unicode);
  await input.fill(''); await apply.click();
  await expect(value).toBeEmpty();
  await expect(page.getByLabel('Octets', { exact: true })).toHaveText('0');
  await page.getByRole('button', { name: 'Keep last 2' }).click();
  await expect(value).toBeEmpty();
  expect(errors).toEqual([]);
});
