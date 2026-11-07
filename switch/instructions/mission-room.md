# Mission room

This room exists for one mission. The brief is in the document "mission-brief".
The owner may not be watching this room; HQ mirrors key events to their phone.

- hands is a program holding the `hands` role. Address @hands with one grammar command
  per line. It answers with ✅ / ⛔ / ⏳ / ⚠️ receipts.
- Risky hands commands (commit, push, close all, scripts marked confirm) wait for the
  owner's approval code. Never try to approve on the owner's behalf.
- `@hands status` returns the project path and dev server URL.
- Time zone: Asia/Kolkata. Never narrate plumbing.
