"""Exercise a built examples/web project in installed Playwright browsers."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("project", type=Path, help="generated web project containing dist and node_modules")
parser.add_argument("--browsers-path", type=Path)
args = parser.parse_args()
project = args.project.resolve()
repo = Path(__file__).resolve().parents[1]
shutil.copyfile(repo / "tests/web-browser.spec.js", project / "tests/web-browser.spec.js")
config = project / "playwright.nex.config.js"
config.write_text('''import { defineConfig, devices } from '@playwright/test';
const development = process.env.NEX_BROWSER_MODE === 'development';
export default defineConfig({
  testDir: './tests', testMatch: 'web-browser.spec.js', workers: 3,
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: { command: 'npm run ' + (development ? 'dev' : 'preview') + ' -- --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173', reuseExistingServer: false },
});
''')
env = dict(os.environ)
if args.browsers_path:
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(args.browsers_path.resolve())
command = [str(project / "node_modules/.bin/playwright"), "test", "--config", str(config)]
for mode, extra in [("production", []), ("development", ["--grep", "renderer rejects"])]:
    print("Testing " + mode + " web output", flush=True)
    subprocess.run(command + extra, cwd=project, env={**env, "NEX_BROWSER_MODE": mode}, check=True)
