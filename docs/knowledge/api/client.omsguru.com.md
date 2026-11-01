# API calls seen on `client.omsguru.com`

What each call is for, and what is safe to do with it, is in
the portal's page in `docs/knowledge/`. Calls that change something (POST / PUT that
save, approve, raise or push) are never made by the agent without the owner's approval.

<!-- AUTO:catalogue -->
Generated 01 Nov 2026 by `scripts/knowledge/learn_netcap.py` from omguru push.json. Names only, no values.

### `POST /channel_companies/fixUpSyncMode/{id}`

- seen 1x, status ?, from page `/channel_companies/edit/{id}`
- body: `{_method, oms_token}`
- in the code: not used yet

### `POST /channel_companies/pushInventory/{id}`

- seen 1x, status ?, from page `/channel_companies/edit/{id}`
- body: `{_method, oms_token}`
- in the code: `omsguru.py`

### `POST /channel_companies/syncCatalogue/{id}`

- seen 1x, status ?, from page `/channel_companies/edit/{id}`
- body: `{_method, oms_token}`
- in the code: not used yet

### `POST /help_desk/client_tickets/get_chat_tool_status`

- seen 8x, status 200, from page `/channel_companies`, `/channel_companies/edit/{id}`
- answer: `{chat_online, chat_status, chat_status_class}`
- in the code: not used yet
<!-- /AUTO:catalogue -->

## Notes (by hand)

- 
