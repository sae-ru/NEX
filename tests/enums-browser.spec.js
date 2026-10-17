import { test, expect } from '@playwright/test';

test('enum application state transitions through every case', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'NEX enum state' })).toBeVisible();
  const status = page.getByRole('status');
  await expect(status).toHaveText('0');
  await page.getByRole('button', { name: 'Increment' }).click();
  await expect(status).toHaveText('1');
  await page.getByRole('button', { name: 'Reset' }).click();
  await expect(status).toHaveText('reset');
  await page.getByRole('button', { name: 'Increment' }).click();
  await expect(status).toHaveText('1');
  await page.getByLabel('Label', { exact: true }).fill('🧠');
  await expect(status).toHaveText('🧠');
  await page.getByRole('button', { name: 'Increment' }).click();
  await expect(status).toHaveText('1');
  await page.reload();
  await expect(status).toHaveText('0');
  expect(errors).toEqual([]);
});
