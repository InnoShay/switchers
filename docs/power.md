# Power mode: open anything, run anything (with your yes)

The desk no longer needs a `desk.yaml` entry for every project or action. Say what you want in
an HQ room; the desk finds it, or asks you first.

## What you can say
- `@hands boot pixelforge` opens any folder under the projects root. It does not have to be in
  `desk.yaml`, and a folder created a minute ago works. Prefixes and typos work too (`pixel`,
  `pixlforge`). Two matches answer `❓ which one? a, b`; none answers `⛔ refused · no project
  called X in <root>`.
- `@hands mission fix-login pixelforge`, `@hands resume pixelforge` use the same lookup.
- `@hands projects` lists configured and discovered projects (max 20).
- Wake sentence: "Room service, let's work on pixelforge" boots it (the word must match the
  folder name exactly and be 4+ letters).
- `@hands exec "npm test -- --watch=false"` runs any shell command, after you approve it.

## How it opens a project
`package.json` with `dev` (else `start`): installs first only if `node_modules` is missing, runs
the dev command in the background, reads the first `http://localhost:<port>` line, opens that
tab, and `shot page` uses it. Xcode projects open in Xcode. Python (Django, FastAPI, Flask,
`__main__`) gets an obvious `uv run`/`python` command. Rust, Go and anything else open the editor
only. If no URL shows up in 45 s a Terminal opens with the command and the usual ports are probed.

## Setup
`export ROOMSERVICE_PROJECTS_DIR=~/cooks` (default). Use a comma list for several roots:
`~/cooks,~/work`. Read at request time, so no restart is needed.

## Safety model
- Fast path unchanged: apps, URLs and scripts still come from the allowlist in `desk.yaml`.
  `@hands open Steam` is still `⛔ refused · open Steam — not on the allowlist`.
- `exec` is the one escape hatch and is never silent. Every `exec` posts
  `⚠️ approval needed · exec "<command>" in <project or ~>` with the full command and a code.
  It runs only after the paired owner replies `ok CODE`. Non-owners and agents cannot send it or
  approve it; codes expire after 5 minutes; `no CODE` drops it.
- Runs with `bash -lc` (the only shell use, see DECISIONS.md), in the active mission's folder,
  else the projects root, else `$HOME`. 120 s timeout. `freeze` kills a running exec.
- Rate limit (20 per minute) and frozen mode apply. Every result is a receipt in chat:
  `✅ approved by <owner> · exit 0` plus the last 15 lines, so the chat is the audit log.
