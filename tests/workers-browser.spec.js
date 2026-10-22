import { test, expect } from '@playwright/test';

test('real module worker returns exact i64 and leaves UI bundle separate', async ({ page }) => {
  const workers = []; page.on('worker', worker => workers.push(worker));
  await page.goto('/'); await expect(page.getByRole('status')).toHaveText('Ready');
  await page.getByRole('button', {name:'Compute',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('9007199254741000 Worker 🧠');
  expect(workers.length).toBe(1); expect(workers[0].url()).toMatch(/worker-entry/);
});

test('UI responds while a worker loops and cancellation permits later work', async ({ page }) => {
  await page.goto('/');
  const pending = page.waitForEvent('worker');
  await page.getByRole('button', {name:'Long task',exact:true}).click(); await pending;
  for (let i=0;i<5;i++) await page.getByRole('button', {name:'Click',exact:true}).click();
  await expect(page.locator('#clicks')).toHaveText('5');
  await expect(page.getByRole('status')).toHaveText('Working');
  await page.getByRole('button', {name:'Cancel',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('E_CANCELED');
  await page.getByRole('button', {name:'Compute',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('9007199254741000 Worker 🧠');
});

test('host deadline stops an infinite worker without freezing events', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', {name:'Timeout',exact:true}).click();
  await page.getByRole('button', {name:'Click',exact:true}).click();
  await expect(page.locator('#clicks')).toHaveText('1');
  await expect(page.getByRole('status')).toHaveText('E_TIMEOUT');
});

test('checked computation trap returns a recoverable completion', async ({ page }) => {
  await page.goto('/');await page.getByRole('button',{name:'Trap',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('E_DIV_ZERO');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('two real workers run while a third queues and cancel_all clears all', async ({ page }) => {
  const workers=[];page.on('worker',worker=>workers.push(worker));
  await page.goto('/');
  for(let i=0;i<3;i++) await page.getByRole('button',{name:'Long task',exact:true}).click();
  await expect.poll(()=>workers.length).toBe(2);
  await page.getByRole('button',{name:'Click',exact:true}).click();
  await expect(page.locator('#clicks')).toHaveText('1');
  await page.getByRole('button',{name:'Cancel all',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('E_CANCELED');
  expect(workers.length).toBe(2);
});
