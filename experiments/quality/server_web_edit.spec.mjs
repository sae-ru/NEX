import { test, expect } from '@playwright/test';

const restarted = process.env.NEX_TEST_PHASE === 'restart';
function credential(testInfo, who = 'alice') {
  return JSON.parse(process.env.NEX_TEST_TOKENS)[testInfo.project.name][who];
}
async function login(page, token) {
  await page.getByLabel('Bearer token').fill(token);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Saved data loaded.');
}
const rows = page => page.getByRole('list', { name: 'Tasks' }).getByRole('listitem');

test('real API CRUD, credentials, isolation, reload and route navigation', async ({ page }, info) => {
  test.skip(restarted);
  await page.goto('/');
  await page.getByLabel('Bearer token').fill('invalid');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Authentication failed');
  await login(page, credential(info));
  await expect(rows(page)).toHaveCount(0);
  await page.getByLabel('New or replacement task text').fill('Сохранённая задача 🦊 <script>');
  await page.getByRole('button', { name: 'Add task', exact: true }).click();
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toContainText('Сохранённая задача 🦊 <script>');
  await rows(page).first().getByRole('button', { name: 'Mark complete' }).click();
  await expect(rows(page).first().getByRole('button', { name: 'Mark active' })).toBeVisible();
  await page.getByRole('link', { name: 'Active tasks', exact: true }).click();
  await expect(rows(page)).toHaveCount(0);
  await page.goBack();
  await expect(rows(page)).toHaveCount(1);
  await page.reload();
  await expect(page.getByLabel('Bearer token')).toHaveValue('');
  await login(page, credential(info));
  await expect(rows(page)).toHaveCount(1);
  await page.getByLabel('New or replacement task text').fill('Updated Я🦊');
  await rows(page).first().getByRole('button', { name: 'Replace text' }).click();
  await expect(rows(page).first()).toContainText('Updated Я🦊');
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await login(page, credential(info, 'bob'));
  await expect(rows(page)).toHaveCount(0);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await login(page, credential(info));
  await expect(rows(page)).toHaveCount(1);
  await rows(page).first().getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(rows(page)).toHaveCount(0);
  await page.getByLabel('New or replacement task text').fill('persist-' + info.project.name);
  await page.getByRole('button', { name: 'Add task', exact: true }).click();
  await expect(rows(page)).toHaveCount(1);
});

test('cancel and sign-out discard late responses across credentials', async ({ page }, info) => {
  test.skip(restarted);
  await page.goto('/');
  await login(page, credential(info, 'bob'));
  let release, entered;
  let gate = new Promise(resolve => { release = resolve; });
  let started = new Promise(resolve => { entered = resolve; });
  await page.route('**/api/tasks', async route => {
    entered(); await gate;
    await route.fulfill({ contentType: 'application/json', body: '[{"id":"99","text":"STALE_USER_DATA","complete":false}]' }).catch(() => {});
  }, { times: 1 });
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await started;
  await expect(page.getByRole('status')).toHaveText('Loading...');
  await page.getByRole('button', { name: 'Cancel request', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('E_CANCELED');
  release();
  await page.unrouteAll({ behavior: 'wait' });
  await expect(rows(page)).toHaveCount(0);
  gate = new Promise(resolve => { release = resolve; });
  started = new Promise(resolve => { entered = resolve; });
  await page.route('**/api/tasks', async route => {
    entered(); await gate;
    await route.fulfill({ contentType: 'application/json', body: '[{"id":"99","text":"STALE_USER_DATA","complete":false}]' }).catch(() => {});
  }, { times: 1 });
  await page.getByRole('button', { name: 'Refresh', exact: true }).click(); await started;
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await login(page, credential(info));
  release(); await page.unrouteAll({ behavior: 'wait' });
  await expect(page.getByText('STALE_USER_DATA')).toHaveCount(0);
  await expect(page.getByRole('status')).toHaveText('Saved data loaded.');
});

test('network, schema, Unicode, body limit, redirect and timeout errors are recoverable', async ({ page }, info) => {
  test.skip(restarted);
  await page.goto('/'); await login(page, credential(info, 'bob'));
  async function faulty(handler, message) {
    let entered, release;
    const started = new Promise(resolve => { entered = resolve; });
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/api/tasks', async route => {
      entered(); await gate; await handler(route);
    }, { times: 1 });
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await started;
    // Consecutive failures can have the same text. Keep this response held
    // until the new request's loading state replaces the previous outcome.
    await expect(page.getByRole('status')).toHaveText('Loading...');
    release();
    await expect(page.getByRole('status')).toContainText(message);
    await page.unrouteAll({ behavior: 'wait' });
    await expect(rows(page)).toHaveCount(0);
  }
  await faulty(route => route.abort('failed'), 'E_NETWORK');
  await faulty(route => route.fulfill({ contentType: 'application/json', body: '[{"id":1,"text":"bad i64","complete":false}]' }), process.env.NEX_TEST_TYPED_API ? 'E_JSON' : 'Invalid task response');
  const noncanonical = [{ id: '1\n', text: 'trailing line terminator', complete: false }];
  await faulty(route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(process.env.NEX_TEST_TYPED_API ? { ok: noncanonical } : noncanonical) }), process.env.NEX_TEST_TYPED_API ? 'E_JSON' : 'Invalid task response');
  await faulty(route => route.fulfill({ contentType: 'application/json', body: '\ufeff' + (process.env.NEX_TEST_TYPED_API ? '{"ok":[]}' : '[]') }), 'Saved data loaded.');
  await faulty(route => route.fulfill({ body: Buffer.from([0xc0, 0x80]) }), 'E_UTF8');
  await faulty(route => route.fulfill({ body: 'x'.repeat(1048577) }), 'E_LIMIT');
  // WebKit cannot synthesize redirect status with route.fulfill. Use a real
  // same-origin 302 from the test proxy in every browser instead.
  await faulty(route => route.continue({ url: new URL('/api/redirect', page.url()).href }), 'E_NETWORK');
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/api/tasks', async route => {
    await gate; await route.fulfill({ contentType: 'application/json', body: '[]' }).catch(() => {});
  }, { times: 1 });
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('E_TIMEOUT', { timeout: 10000 });
  release(); await page.unrouteAll({ behavior: 'wait' });
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Saved data loaded.');
});

test('committed data survives native server restart', async ({ page }, info) => {
  test.skip(!restarted);
  await page.goto('/'); await login(page, credential(info));
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toContainText('persist-' + info.project.name);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await login(page, credential(info, 'bob'));
  await expect(rows(page)).toHaveCount(0);
});


test('quality edit enforces Unicode scalar bound in client and hostile request', async ({page,browser},info) => {
  test.skip(restarted);
  await info.attach('engine', {body: JSON.stringify({engine:info.project.name,version:browser.version()}),contentType:'application/json'});
  const maximum=Number(process.env.NEX_QUALITY_TEXT_MAX);
  expect([64,2000]).toContain(maximum);
  await page.goto('/'); await login(page,credential(info,'bob'));
  await expect(rows(page)).toHaveCount(0);
  await page.getByLabel('New or replacement task text').fill('🦊'.repeat(maximum));
  await page.getByRole('button',{name:'Add task',exact:true}).click();
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first().locator('.task-text')).toHaveText('🦊'.repeat(maximum));
  await rows(page).first().getByRole('button',{name:'Delete',exact:true}).click();
  await expect(rows(page)).toHaveCount(0);
  let posts=0;
  page.on('request',r=>{if(r.method()==='POST' && new URL(r.url()).pathname==='/api/tasks')posts++;});
  await page.getByLabel('New or replacement task text').fill('🦊'.repeat(maximum+1));
  await page.getByRole('button',{name:'Add task',exact:true}).click();
  await expect(page.getByRole('status')).toContainText(`1..${maximum}`);
  expect(posts).toBe(0); await expect(rows(page)).toHaveCount(0);
  const stale=await page.request.post('/api/tasks',{headers:{Authorization:'Bearer '+credential(info,'bob')},data:{text:'🦊'.repeat(maximum+1)}});
  expect(stale.status()).toBe(422);
  const listed=await page.request.get('/api/tasks',{headers:{Authorization:'Bearer '+credential(info,'bob')}});
  expect(await listed.json()).toEqual({ok:[]});
});
