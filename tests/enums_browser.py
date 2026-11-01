"""Opt-in browser interaction against a built examples/enums/web.nex app."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('project', type=Path)
parser.add_argument('--browsers-path', type=Path)
args = parser.parse_args()
project = args.project.resolve()
repo = Path(__file__).resolve().parents[1]
shutil.copyfile(repo/'tests/enums-browser.spec.js', project/'tests/enums-browser.spec.js')
config = project/'playwright.enums.config.js'
config.write_text('''import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
 testDir:'./tests',testMatch:'enums-browser.spec.js',workers:3,
 use:{baseURL:'http://127.0.0.1:4173',trace:'retain-on-failure'},
 projects:[{name:'chromium',use:{...devices['Desktop Chrome']}},
           {name:'firefox',use:{...devices['Desktop Firefox']}},
           {name:'webkit',use:{...devices['Desktop Safari']}}],
 webServer:{command:'npm run preview -- --port 4173 --strictPort',url:'http://127.0.0.1:4173',reuseExistingServer:false},
});
''', newline="\n")
env = dict(os.environ)
if args.browsers_path: env['PLAYWRIGHT_BROWSERS_PATH'] = str(args.browsers_path.resolve())
subprocess.run([str(project/'node_modules/.bin/playwright'),'test','--config',str(config)],cwd=project,env=env,check=True)
