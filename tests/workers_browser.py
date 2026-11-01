"""Opt-in actual production module workers in Chromium, Firefox and WebKit."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('project',type=Path)
parser.add_argument('--browsers-path',type=Path)
parser.add_argument('--structured-tasks',action='store_true')
args=parser.parse_args();project=args.project.resolve();repo=Path(__file__).resolve().parents[1]
shutil.copyfile(repo/'tests/workers-browser.spec.js',project/'tests/workers-browser.spec.js')
if args.structured_tasks:
    with (project/'tests/workers-browser.spec.js').open('a') as spec:
        spec.write('''
test('task scheduler has an independent bounded lifetime and later jobs succeed', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button',{name:'Long task',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText(/E_LIMIT|E_TIMEOUT/,{timeout:12000});
  await page.getByRole('button',{name:'Compute',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('9007199254741000 Worker 🧠');
});
''')
config=project/'playwright.workers.config.js'
config.write_text('''import {defineConfig,devices} from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'workers-browser.spec.js',workers:3,
 timeout:30000,expect:{timeout:15000},reporter:[['list'],['json',{outputFile:'workers-browser-results.json'}]],
 use:{baseURL:'http://127.0.0.1:4197',trace:'retain-on-failure'},
 projects:[{name:'chromium',use:{...devices['Desktop Chrome']}},
 {name:'firefox',use:{...devices['Desktop Firefox']}},{name:'webkit',use:{...devices['Desktop Safari']}}],
 webServer:{command:'npm run preview -- --port 4197 --strictPort',url:'http://127.0.0.1:4197',reuseExistingServer:false}});
''', newline="\n")
env=dict(os.environ)
if args.browsers_path:env['PLAYWRIGHT_BROWSERS_PATH']=str(args.browsers_path.resolve())
subprocess.run([str(project/'node_modules/.bin/playwright'),'test','--config',str(config)],cwd=project,env=env,check=True)
