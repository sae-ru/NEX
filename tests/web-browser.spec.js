import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => { await page.goto('/'); });

test('compiled application mounts and updates state with Unicode input', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await expect(page).toHaveTitle('NEX Tasks');
  await expect(page.getByRole('heading', { name: 'NEX Tasks' })).toBeVisible();
  await expect(page.getByRole('status')).toHaveText('1 active');
  await page.getByLabel('New task', { exact: true }).fill('Проверить 🦊 NEX');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();
  await expect(page.getByRole('listitem')).toHaveCount(2);
  await expect(page.getByRole('listitem').nth(1)).toContainText('Проверить 🦊 NEX');
  await expect(page.getByLabel('New task', { exact: true })).toHaveValue('');
  await expect(page.getByRole('status')).toHaveText('2 active');
  expect(errors).toEqual([]);
});

test('toggle/delete transitions preserve remaining items and accessible controls', async ({ page }) => {
  const draft = page.getByLabel('New task', { exact: true });
  await draft.fill('Keep this item'); await draft.press('Enter');
  await page.getByRole('button', { name: 'Mark complete', exact: true }).first().click();
  await expect(page.getByRole('status')).toHaveText('1 active');
  await expect(page.getByRole('button', { name: 'Mark active', exact: true })).toHaveCount(1);
  await page.getByRole('button', { name: 'Delete', exact: true }).first().click();
  await expect(page.getByRole('listitem')).toHaveCount(1);
  await expect(page.getByRole('listitem')).toContainText('Keep this item');
  await draft.fill(''); await draft.press('Enter');
  await expect(page.getByRole('listitem')).toHaveCount(1);
});

test('URL navigation, browser back and route reload work', async ({ page }) => {
  await page.getByRole('button', { name: 'Mark complete', exact: true }).click();
  await page.getByRole('link', { name: 'Active tasks', exact: true }).click();
  await expect(page).toHaveURL(/\/active$/);
  await expect(page.getByRole('listitem')).toHaveCount(0);
  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('listitem')).toHaveCount(1);
  await page.goto('/active');
  await expect(page.getByRole('listitem')).toHaveCount(1);
  await expect(page.getByRole('heading', { name: 'NEX Tasks' })).toBeVisible();
});

test('forms and navigation are keyboard accessible', async ({ page, browserName }) => {
  // macOS WebKit's default link-focus preference uses Option+Tab for full traversal.
  // https://developer.apple.com/documentation/webkit/wkpreferences/tabfocuseslinks
  const next = browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab';
  await page.getByRole('link', { name: 'All tasks', exact: true }).focus();
  await page.keyboard.press(next);
  await expect(page.getByRole('link', { name: 'Active tasks', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/active$/);
  await page.keyboard.press(next);
  await expect(page.getByLabel('New task', { exact: true })).toBeFocused();
  await page.keyboard.type('Keyboard task'); await page.keyboard.press('Enter');
  await expect(page.getByRole('listitem')).toHaveCount(2);
  await expect(page.getByLabel('New task', { exact: true })).toBeFocused();
});

test('text is escaped and does not become executable HTML', async ({ page }) => {
  const payload = '<img src=x onerror="window.nexInjected=true">';
  await page.getByLabel('New task', { exact: true }).fill(payload);
  await page.getByRole('button', { name: 'Add task', exact: true }).click();
  await expect(page.getByRole('listitem').nth(1)).toContainText(payload);
  await expect(page.locator('img')).toHaveCount(0);
  expect(await page.evaluate(() => window.nexInjected)).toBeUndefined();
});

test('mobile layout fits viewport and retains working controls', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.getByLabel('New task', { exact: true }).fill('Mobile task');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();
  await expect(page.getByRole('listitem')).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('renderer rejects unsupported markup, URLs and prototype event names', async ({ page }) => {
  test.skip(process.env.NEX_BROWSER_MODE !== 'development', 'direct renderer checks use the development module');
  const errors = await page.evaluate(async () => {
    const { renderView } = await import('/src/renderer.tsx');
    const base = { tag: 'div', text: '', attributes: [], events: [], children: [] };
    const cases = [
      { ...base, tag: 'script' },
      { ...base, attributes: [{ name: 'onclick', value: 'alert(1)' }] },
      { ...base, attributes: [{ name: 'style', value: 'position:fixed' }] },
      { ...base, attributes: [{ name: 'href', value: 'javascript:alert(1)' }] },
      { ...base, attributes: [{ name: 'href', value: ' java\nscript:alert(1)' }] },
      { ...base, attributes: [{ name: 'src', value: 'data:text/html,evil' }] },
      ...['constructor', '__proto__', 'toString'].map(event => ({ ...base, events: [{ event, action: 'test' }] })),
    ];
    return cases.map(value => { try { renderView(value, () => {}); return 'accepted'; } catch (error) { return error.code; } });
  });
  expect(errors).toEqual(Array(9).fill('E_UI'));
});
