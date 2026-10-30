# Ultron Phone

The Bindal agent's Android app (was "SMS to Sheet"). Two jobs:

1. **Agent mode** - the phone works for the bots when a PC cannot: www.myntra.com refuses GitHub's
   runners (HTTP 403), so when the office PC is off the Myntra zero TD run (10 AM / 2 PM / 5 PM) runs
   on GitHub and hands its style lookups to the phone, which checks them on its own mobile line and
   sends the answers back. A foreground service (notification "Ultron Phone: agent on") asks the
   Telegram worker for work every minute (`POST /api/phone/next`, worker/src/worker.js) and answers a
   part at a time (`/api/phone/result`). Comes back on by itself after a reboot.
2. **SMS to sheet** - every incoming SMS (optionally only some senders) is added to a Google Sheet
   through an Apps Script web app, with the SIM it came in on ("SIM 1" / "SIM 2"), so the returns OTPs
   on the second SIM can be read from the sheet later. Event-driven (`SMS_RECEIVED`), uploaded by
   WorkManager once online, retried with backoff, never twice (the script skips duplicates).

## Install / update

The APK is built on GitHub (`.github/workflows/android-app.yml`, on every change to this folder or
by hand), never on a PC. It lands in Drive **AGENT WORK/ULTRON PHONE/Ultron Phone.apk** and Telegram
gets the link. On the phone: open the link, download, install (allow "Install unknown apps" once).
Every build is signed with the same key (kept in that Drive folder), so a new APK installs over the
old one and keeps its settings. The old "SMS to Sheet" app is a different app: uninstall it once
Ultron Phone works.

## Set up on the phone

1. **Agent connection**: Worker URL `https://bindal-telegram-bot.bhikan-serein.workers.dev` and the
   worker's `DASHBOARD_TOKEN` (the same token as in the repo's `.env`). Save settings.
2. Turn **Agent mode** on (allow notifications). The dot turns green after the first check-in.
3. **Phone setup**: Battery -> allow (no battery optimisation). Xiaomi / Oppo / Vivo / Realme:
   App settings -> Autostart on.
4. **SMS to sheet** (optional, for the OTPs later): see below, then Allow SMS (Android 13+: if it is
   greyed out, App info -> ⋮ -> Allow restricted settings first), Send test row. **Import old SMS**
   sends the inbox of the last 60 days (Senders filter applies; anything already in the sheet is skipped).

## SMS sheet (Google Sheet + Apps Script)

1. A Google Sheet -> Extensions -> Apps Script, the code of `apps-script/Code.gs`.
2. In `setupSecret()` put a long random key, run it once, allow the permissions.
3. Run `testInsert`: a header row and a test row appear in the `SMS` tab.
4. Deploy -> New deployment -> Web app, execute as Me, access Anyone; copy the `/exec` URL into the app
   with the same key. Later script changes: Manage deployments -> Edit -> New version (same URL).

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
