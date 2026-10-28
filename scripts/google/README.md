# Google Drive OAuth token

The service account cannot create files in a personal Drive (no storage quota), so the bots use
Drive as the Drive owner's account, through an OAuth refresh token. Make it once, and again only
if it is revoked (Telegram then shows "invalid_grant").

1. Google Cloud console, the service account's project:
   * APIs & Services > Library: **Google Drive API** enabled.
   * OAuth consent screen: External; add your Gmail as a test user; then **Publish app**
     (In production). A token of an app left in Testing stops working after 7 days.
   * Credentials > Create credentials > OAuth client ID > **Desktop app** > Download JSON.
2. `python scripts/google/oauth_token.py path/to/client_secret.json`
   A browser opens: sign in with the account that owns the Drive folders and allow access (an
   unverified-app warning is expected: Advanced > Go to ...).
3. The three printed values go into `.env` and on GitHub:
   `gh secret set GOOGLE_OAUTH_CLIENT_ID`, `gh secret set GOOGLE_OAUTH_CLIENT_SECRET`,
   `gh secret set GOOGLE_OAUTH_REFRESH_TOKEN`.

Keep the downloaded client JSON out of the repository.
