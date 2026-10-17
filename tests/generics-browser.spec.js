import { test, expect } from '@playwright/test';

test('generic state and a specialized pure transition update the browser', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', {name:'NEX generic state'})).toBeVisible();
  const status = page.getByRole('status');
  await expect(status).toHaveText('seed: 0');
  await page.getByLabel('Value', {exact:true}).fill('🧠');
  await expect(status).toHaveText('🧠: 1');
  await page.getByRole('button', {name:'Increment'}).click();
  await expect(status).toHaveText('🧠: 2');
  await page.getByRole('button', {name:'Reset'}).click();
  await expect(status).toHaveText('seed: 0');
  await page.reload();
  await expect(status).toHaveText('seed: 0');
  expect(errors).toEqual([]);
});
