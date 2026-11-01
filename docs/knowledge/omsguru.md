# OMSGuru web app (`client.omsguru.com`) — what the calls are for

Learned from the owner's capture of 20 Oct 2026 (channel settings page). Field-level detail:
`api/client.omsguru.com.md`. Login and the calls the bots already use: `docs/PORTALS.md`.

All three are form posts from the channel's edit page (`/channel_companies/edit/{channel id}`) with
`_method` and the page's `oms_token` (CSRF token, read from the page); they answer with a redirect.

| Call | Kind | What it does | Used by |
|---|---|---|---|
| `POST /channel_companies/pushInventory/{channel}` | **Changes** | pushes OMSGuru stock to that channel (the "Push Inventory" button) | `inv-push` every 3 hours, `/invpush` |
| `POST /channel_companies/syncCatalogue/{channel}` | **Changes** | pulls the channel's catalogue into OMSGuru ("Sync Catalogue") | not used; a fix for listings missing in OMSGuru (`listings`), only with approval |
| `POST /channel_companies/fixUpSyncMode/{channel}` | **Changes** | resets the channel's sync mode ("Fix sync mode") | not used; a possible fix when a push keeps failing, only with approval |

`POST /help_desk/client_tickets/get_chat_tool_status` is the help-desk chat widget (noise).
