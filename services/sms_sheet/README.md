# SMS sheet (Phone OTP Sheet 2026)

Every SMS of a phone in the ULTRON app's SMS only mode lands here, through the Telegram worker's
`POST /api/sms` (`docs/bots/worker-and-dashboard.md`): the worker holds this web app's URL and key
(`SMS_WEBAPP_URL`, `SMS_WEBAPP_KEY`), so phones need no setup. `Code.gs` files a courier's returns OTP in
the team's Daily OTP sheet and the POD in Drive (its header explains). It came from the old Ultron Phone app
(removed 23 Nov 2026); version 17 is deployed.


22 Nov 2026: the sheet also takes SMS from the Ultron app's "SMS only" mode, through the Telegram worker's
`POST /api/sms` (`docs/bots/worker-and-dashboard.md`). The worker holds the URL and the key, so a phone needs
no setup; the phone's name goes in the new **User** column (H). Code.gs version 17 is deployed at the same URL.

23 Nov 2026 (owner): in the Daily OTP sheet the name column of the agent's rows holds only the phone's user name
(e.g. `Bhikan`, no `Agent ·`). The agent's mark is now the note `ULTRON app` on that name cell; rows written
before still read `Agent · <name>` and count as the agent's too. The team's rows and the Myntra OTP bot's rows
(found by portal and courier tag, not by name) are never changed. Needs a new version of the deployment.

1. A Google Sheet -> Extensions -> Apps Script, the code of `apps-script/Code.gs`.
2. In `setupSecret()` put a long random key, run it once, allow the permissions. In Project Settings ->
   Script Properties add `OTP_SHEET_ID` and `AGENT_WORK_ID` (the same ids as the GitHub variables
   `MYNTRA_OTP_SHEET_ID` and `AGENT_WORK_FOLDER_ID`); do this before deploying this code over an older version.
3. Run `testInsert`: a header row and a test row appear in the `SMS` tab.
4. Deploy -> New deployment -> Web app, execute as Me, access Anyone; copy the `/exec` URL into the app
   with the same key. Later script changes: Manage deployments -> Edit -> New version (same URL);
   after one that needs new permissions run `authorize` once from the editor.

## Log

| Line | Meaning |
|---|---|
| Agent on / off | Agent mode started / stopped |
| Agent: worker not reached | no internet, or wrong worker URL / token (`token refused`) |
| Job ... : N Myntra styles | the phone took a bot's job |
| Job ... done: X of N styles answered | answers sent back to the bot |
| SMS queued / SENT / DUPLICATE | SMS waiting / added to the sheet / already there |
| SMS skipped (filter) | sender not in the Senders list |
| RETRY | network or script issue, tried again by itself |

## Code

`AgentService.kt` (the agent loop), `MyntraLookup.kt` (the same lookup as
`src/ultron/workings/myntra_zero_td/spider.py`), `SmsReceiver.kt` + `UploadWorker.kt` (SMS to sheet),
`BootReceiver.kt`, `MainActivity.kt` + `res/layout/activity_main.xml`, `Prefs.kt`. The bot side:
`src/ultron/workings/core/phone.py`.

Not for the Play Store (Google keeps SMS permissions for default SMS apps); sideloaded only.
