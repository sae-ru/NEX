import { test, expect } from '@playwright/test';

test('floating state, generic arithmetic and a captured callback update the UI', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'NEX finite numbers' })).toBeVisible();
  const value = page.getByRole('status');
  await expect(value).toHaveText('2.5e-1');
  await page.getByRole('button', { name: 'Add 0.5' }).click();
  await expect(value).toHaveText('7.5e-1');
  await page.getByRole('button', { name: 'Add 0.5' }).click();
  await expect(value).toHaveText('1.25e0');
  await page.getByRole('button', { name: 'Double', exact: true }).click();
  await expect(value).toHaveText('2.5e0');
  await expect(page.getByLabel('History')).toHaveText('[2.5e-1,7.5e-1,1.25e0,2.5e0]');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(value).toHaveText('2.5e-1');
  await expect(page.getByLabel('History')).toHaveText('[2.5e-1]');
  await page.reload();
  await expect(value).toHaveText('2.5e-1');
  expect(errors).toEqual([]);
});

test('numeric JSON preserves binary64 edges and rejects invalid edits without changing state', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  const value = page.getByRole('status');
  const input = page.getByLabel('JSON number', { exact: true });
  const apply = page.getByRole('button', { name: 'Apply', exact: true });
  for (const [source, display] of [
    ['5e-324', '5e-324'], ['-0', '0e0'],
    ['9007199254740993', '9.007199254740992e15'],
    ['2.2250738585072014e-308', '2.2250738585072014e-308'],
    ['1.7976931348623157e308', '1.7976931348623157e308'],
    ['1.5', '1.5e0'],
  ]) {
    await input.fill(source);
    await apply.click();
    await expect(value).toHaveText(display);
    await expect(page.getByRole('alert')).toBeEmpty();
  }
  const history = await page.getByLabel('History').textContent();
  for (const source of ['"1.5"', 'true', 'null', '1e309', '01', 'NaN']) {
    await input.fill(source);
    await apply.click();
    await expect(page.getByRole('alert')).toHaveText('E_JSON');
    await expect(value).toHaveText('1.5e0');
    await expect(page.getByLabel('History')).toHaveText(history);
  }
  await input.fill('5e-324');
  await apply.click();
  await page.getByRole('button', { name: 'Double', exact: true }).click();
  await expect(value).toHaveText('1e-323');
  await expect(page.getByRole('alert')).toBeEmpty();
  expect(errors).toEqual([]);
});
