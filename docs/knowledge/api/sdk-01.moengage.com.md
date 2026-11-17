# API calls seen on `sdk-01.moengage.com`

What each call is for, and what is safe to do with it, is in
the portal's page in `docs/knowledge/`. Calls that change something (POST / PUT that
save, approve, raise or push) are never made by the agent without the owner's approval.

<!-- AUTO:catalogue -->
Generated 14 Nov 2026 by `scripts/knowledge/learn_netcap.py` from fl listing file download price update .json, fl rate cart.json, flipkartcap.json. Names only, no values.

### `POST /v3/campaigns/inapp/live`

- seen 6x, status 200, from page `/index.html`
- query: `os`, `sdk_ver`, `unique_id`
- body: `{identifiers: {user_identities: {uid}, previous_identities: {}, uid}, campaign_ids: […], user_session_attributes: {tab, state, USER_TYPE, DAY_OF_THE_WEEK, TIME_OF_THE_DAY}}`
- answer: `{campaigns: [{display: {config: {…}, rules: {…}}, delivery: {dismiss_interval, persistent, priority, fc_meta: {…}}, status, tags: […], trigger: {url_condition: {…}, primary_condition: {…}}, expiry_time, updated_time, template_type, campaign_id, campaign_name, user_in_segment, campaign_type, trigger_type, campaign_context: {cid, campaign_name, moe_locale_name, moe_locale_id, moe_variation_id}}], min_delay_btw_inapps, sync_interval, fc_settings: {}}`
- in the code: not used yet

### `POST /v3/campaigns/inapp/live/{id}`

- seen 4x, status 200, from page `/index.html`
- query: `os`, `sdk_ver`, `unique_id`
- body: `{contexts: […], campaign_context: {cid, campaign_name, moe_locale_name, moe_locale_id, moe_variation_id}, user_session_attributes: {USER_TYPE, DAY_OF_THE_WEEK, TIME_OF_THE_DAY}, event: {name, attributes: {timestamp, moe_logged_in_status, moe_first_visit, URL}, time}, identifiers: {user_identities: {uid}, previous_identities: {}, uid}}`
- answer: `{position, payload_type, payload, editor_version, template_type, campaign_context: {cid, campaign_name, moe_locale_name, moe_locale_id, moe_variation_id, moe_campaign_tags: […]}, campaign_meta: {brz_version}, frequency_data: {}}`
- in the code: not used yet
<!-- /AUTO:catalogue -->

## Notes (by hand)

- 
