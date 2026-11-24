# Pending app fixes and updates (24 Nov)
Recovered the prior Codex request: fix workspace permissions, atomic approvals, overlapping phone jobs and app chat model errors; expose model selection and add Cloudflare in-app updates. Existing uncommitted edits belong to that work.
Implemented so far: worker/phone.js uses independent D1 job/result rows; migration 0008 includes phone and approval tables. Approval decisions claim a D1 row before dispatch; app chat rethrows model errors for failed job status.
Implementation now includes visible provider/model selection, Profile shortcut, startup update banner, Profile update checks and Android size/digest/package/version verification with system installation confirmation.
CI uploads completed packages in multipart chunks; D1 manifests advance monotonically. Desktop download handoff uses Flutter url_launcher 6.3.3.
Local Flutter analysis, 37 app tests and release web compilation passed. All 234 Python tests and 19 app API integration tests passed. Both D1 migrations applied remotely; operations worker and app API deployed. R2 bucket binding is deliberately absent until account activation.
R2 account is not enabled (Cloudflare error 10042); user asked to enable it while implementation continues. Do not claim release storage is live until verified.
