# API calls seen on `seller.flipkart.com`

What each call is for, and what is safe to do with it, is in
the portal's page in `docs/knowledge/`. Calls that change something (POST / PUT that
save, approve, raise or push) are never made by the agent without the owner's approval.

<!-- AUTO:catalogue -->
Generated 01 Nov 2026 by `scripts/knowledge/learn_netcap.py` from flipkartcap.json. Names only, no values.

### `GET /fed-ads/navbar/seller`

- seen 5x, status 200, from page `/index.html`
- query: `sellerId`
- answer: `{success, data: [{toShow, label, haveTag, tagProps: {tagStyle, tagText}, id, subMenuItems: [{…}]}]}`
- in the code: not used yet

### `GET /getExperimentVariant`

- seen 3x, status 200, from page `/index.html`
- query: `expName`, `fallbackValue`, `parameter`
- in the code: not used yet

### `GET /getFeaturesForSeller`

- seen 3x, status 200, from page `/index.html`
- answer: `{isWebView, sellerType, chatStatus, enableAlerts, sellerId, sellerDetails: {age, sellerId, status, emailId, contacts: [{name, mobileNumber, contactType, email, sellerId}], displayName, city, pincode, phoneNumber, sellerName, newStatus, tnsBlacklisted, tier: {support}}, csrfToken, allLinksEnabled, featureConfig, redirectState, sellerIdQuery, feature: {reports, singleProductListing, orderManagement}, isDcsCallFailed, isOnBehalf, onBehalfEmail, onBehalfHomePage, enableDropShipment, enableGamificationFlow, isDropShipmentEnabled, isMPSSeller, autoInvoicing, googleAnalyticsId, fbfEnabled, enablePayments, enableOldReturns, enableRTM, enableStaticHomepage, globalConfigStr: {googleAnalyticsId, kissmetricsId, gaUid}, chatCategory, chatUrl, ssChannelName, onboardingDownTime, gaLabelPrefix, ssContactN`
- in the code: `flipkart.py`

### `GET /index.html`

- seen 6x, status ?, from page `/index.html`
- body: `{}`
- in the code: `flipkart.py`

### `GET /napi/darwin/finalTier`

- seen 1x, status 200, from page `/index.html`
- answer: `{tier, tierChangeInfo, tieredOn, nextTierDate, tieredFrom, tierEffectiveFrom, breaches: {value, tier, benchmark: {gold, diamond, silver, bronze}}, cancellation: {value, tier, benchmark: {gold, diamond, silver, bronze}}, revenue: {value, tier, benchmark: {platinum, diamond, gold, silver, bronze, wood}}, units: {value, tier, benchmark: {platinum, diamond, gold, silver, bronze, wood}}, returns: {value, tier, benchmark: {platinum, diamond, gold, silver, bronze, wood}}, productRatings: {value, tier, benchmark: {platinum, diamond, gold, silver, bronze, wood}}}`
- in the code: not used yet

### `POST /napi/fdp/batch-events`

- seen 9x, status 200, from page `/index.html`
- query: `sellerId`
- body: `{data: {seller_dashboard_performance: [{schemaVersion, eventTime, eventId, updatedAt, data: {…}}]}, namespace, eventName, sellerId}`
- answer: `{status, traceId}`
- in the code: not used yet

### `GET /napi/fkgrowthcapital/es-discovery`

- seen 1x, status 200, from page `/index.html`
- query: `loanType`, `sellerId`
- answer: `{result: {esOffer: {}}}`
- in the code: not used yet

### `GET /napi/fkgrowthcapital/getOffers`

- seen 1x, status 200, from page `/index.html`
- query: `format`
- in the code: not used yet

### `GET /napi/get-locations`

- seen 1x, status 200, from page `/index.html`
- query: `capabilities`, `include`, `locationType`
- answer: `{result: {multiLocationList: [{value, name, locationId, locationType, locationName, locationDesc, entityId, state, capabilities: [{…}], rtdCutOff: […]}]}}`
- in the code: not used yet

### `GET /napi/get-notifications-count`

- seen 2x, status 200, from page `/index.html`
- query: `mode`, `notificationStatus`, `priority[]`
- answer: `{request: {mode, actorExternalId, actorType, status: […], notificationRead, actionTaken, priority: […], priorityBelow, priorityAbove, urgencyBelow, urgencyAbove, domains: […], regions: […], startDate, endDate}, count}`
- in the code: not used yet

### `GET /napi/getSellerStoriesDetails`

- seen 2x, status 200, from page `/index.html`
- answer: `{data: {seller_id, fact_date, data: {impressions_growth, orders_growth, Unnamed: 6, bbd_impressions, static, bbd_orders}}}`
- in the code: not used yet

### `POST /napi/graphql`

- seen 148x, status 200, from page `/`, `/index.html`
- body: `{operationName, variables: {bucketName, type}, query}`
- answer: `{type, error}`
- in the code: not used yet

### `GET /napi/listing/getSellerMPAffinityFlag`

- seen 2x, status 500, from page `/index.html`
- query: `profile_ids`, `sellerId`, `signal_names`
- answer: `{error: {message}}`
- in the code: not used yet

### `GET /napi/listing/mspEnabled`

- seen 4x, status 200, from page `/index.html`
- in the code: not used yet

### `GET /napi/metrics/bizReport/downloadReport/{id}`

- seen 5x, status 200, from page `/index.html`
- query: `sellerId`, `token`
- in the code: not used yet

### `POST /napi/metrics/bizReport/getReportsCount`

- seen 25x, status 200, from page `/index.html`
- body: `{reportGroup, reportName, enable, status, repeat_report_group_name, repeat_report_name, repeat_enable}`
- answer: `{one_time_reports_count, repeat_report_request_count}`
- in the code: not used yet

### `POST /napi/metrics/bizReport/getScheduledReports`

- seen 6x, status 200, from page `/index.html`
- body: `{repeat_report_group_name, repeat_report_name, repeat_enable, page_size, starting_page}`
- answer: `{has_more, schedule_response_list: [{schedule_id, seller_id, report_group_name, report_name, type, frequency, start_date, next_trigger, subscription}]}`
- in the code: not used yet

### `GET /napi/metrics/bizReport/report/2/detail`

- seen 7x, status 200, from page `/index.html`
- query: `reportName`
- answer: `{name, description, filters: [{name, display_name, data_type, values: [{…}], min_value, max_value, operator, allowed_groups: […]}], file_format, schedule_report_filter: {start_date, end_date, schedule_types: […]}}`
- in the code: not used yet

### `POST /napi/metrics/bizReport/report/getReportsV2`

- seen 21x, status 200, from page `/index.html`
- body: `{reportGroup, reportName, enable, status, page_size, starting_page}`
- answer: `{has_more, report_requests: [{request_id, report_group_name, report_name, created_at, updated_at, size, status, report_request_type, read, file_format, filters: [{…}], eta, eta_v2}]}`
- in the code: `flipkart.py`

### `GET /napi/metrics/bizReport/reportCategories`

- seen 7x, status 200, from page `/index.html`
- answer: `[{report_group_id, type, description, feature_flag}]`
- in the code: not used yet

### `GET /napi/metrics/bizReport/reportsNew`

- seen 13x, status 200, from page `/index.html`
- query: `reportGroupName`
- answer: `[…]`
- in the code: not used yet

### `POST /napi/metrics/bizReport/submitReport`

- seen 6x, status 200, from page `/index.html`
- query: `reportName`
- body: `{from_date, to_date, file_format, type, filters: [{values: […], operator, name}]}`
- answer: `{request_id: {request_id, eta}}`
- in the code: not used yet

### `GET /napi/metrics/darwin/v3/tiering-metrics`

- seen 6x, status 200, from page `/index.html`
- answer: `{metrics_data: {metrics: {customer_experience: {category: {…}}, sales: {category: {…}}, service_quality: {category: {…}}}, from_date, to_date, end_date, evaluation_date, trending_tier, tier_code, is_new_seller, last_boost_date, go_live_date, cancellation_allowance_applied, seller_cancellation_units, dbd_breach_units, dbd_allowance_applied}, benchmarks: {customer_experience: {product_rating: {tiers: {…}, unit}}, sales: {}, service_quality: {rtd_breaches: {tiers: {…}, unit}, cancellations: {tiers: {…}, unit}}}, tier_list: {1, 2, 3, 4}, finalTier: {seller_id, is_new_seller, type, last_approved_date, last_updated_date, start_date, end_date, tier_reason, version_id, category, message, tier_value, tier, tier_name, metadata: {metrics: {customer_experience: {…}, sales: {…}, service_quality: {…}}, `
- in the code: not used yet

### `GET /napi/partner-master/v0/ads`

- seen 1x, status 200, from page `/index.html`
- query: `page`, `type`
- answer: `{page, ads_details: [{partner_id, partner_category_id, partner_business_name, partner_logo_url, category_id, category_name, category_logo_url, type, price, banner_url, redirect_url, campaign_id}]}`
- in the code: not used yet

### `GET /napi/payments/fetchBlockStatus`

- seen 1x, status 200, from page `/index.html`
- query: `tier`
- answer: `{payment_expected, message_id, message, payout_cycle_change, payout_cycle_message, payment_failed_message, payment_delayed, payment_failed}`
- in the code: not used yet

### `GET /napi/payments/fetchLastPaymentDetails`

- seen 1x, status 200, from page `/index.html`
- answer: `{bifurcation_summary_list: [{bifurcation_details: {order: {…}, protection_fund: {…}, rewards: {…}, service: {…}, taxation: {…}}, allow_prepaid_drill_down, allow_postpaid_drill_down, id, event, reason, aggr_amount: {prepaid, postpaid, total}, prepaid_detail: {utr_number, settlement_status, bank_account_no, utr_label}, postpaid_detail: {utr_number, settlement_status, bank_account_no, utr_label}}], payments: [{start_date, payment_date, end_date, prepaid, postpaid, total_amount}], total, remaining, payment_time, holiday_reason, sync_date, cached}`
- in the code: not used yet

### `GET /napi/payments/fetchOutstandingPaymentDetails`

- seen 1x, status 200, from page `/index.html`
- answer: `{bifurcation_summary_list: [{bifurcation_details: {order: {…}, protection_fund: {…}, rewards: {…}, service: {…}, taxation: {…}}, allow_prepaid_drill_down, allow_postpaid_drill_down, id, event, reason, aggr_amount: {prepaid, postpaid, total}, prepaid_detail, postpaid_detail}], payments: [{start_date, payment_date, end_date, prepaid, postpaid, total_amount}], total, remaining, payment_time, holiday_reason, sync_date, cached}`
- in the code: not used yet

### `GET /napi/payments/fetchSellerStatement`

- seen 1x, status 200, from page `/index.html`
- query: `settlement_type`
- answer: `{statement_detail: {opening_balance, total_balance, net_balance, total_payment, closing_balance, accumulated_amount, settlement_date, payment_type, payment_type_label, settlement_start_date, settlement_end_date, min_date, max_date, open_balance_as_of_date, close_balance_as_of_date, on_board_date, advice_id, utr_number, is_mismatched, mismatched_amount, fasrequired}, fee_classification: {sales: {total_sales: {credit, debit, net_settlement}, refunds: {credit, debit, net_settlement}, ndd_sdd_amount: {credit, debit, net_settlement}, cancellation_fee: {credit, debit, net_settlement}, offers: {customer_discount_by_seller: {…}, customer_discount_total: {…}, aggregated_amount}, aggregated_amount}, spf_payout: {credit, debit, net_settlement}, services: {fee_groups: [{…}], aggregated_amount}, mp_fee`
- in the code: not used yet

### `GET /napi/riddler/fetchAssignedQuestionsCount`

- seen 10x, status 200, from page `/index.html`
- query: `sellerId`
- answer: `{unansweredCount, bookmarkCount}`
- in the code: not used yet

### `GET /napi/seller-capability/fetch-capability`

- seen 8x, status 200, from page `/index.html`
- query: `capabilityName`
- answer: `{CAP_SELLER_LOCKIN}`
- in the code: not used yet

### `GET /napi/sellerBuyerCommunications/isSellerEnabled`

- seen 7x, status 200, from page `/index.html`
- query: `sellerId`
- answer: `{result: {request: {actor_id, actor_type}, enabled, argos_id, chat_listing_scope, perf_policy, multi_agent}}`
- in the code: not used yet

### `GET /napi/srm/getQuestionnaireByFeature`

- seen 4x, status 200, from page `/index.html`
- query: `featureName`
- answer: `{data: {createdAt, updatedAt, createdBy, updatedBy, discoveryId, id, description, questionMappings: [{id, question: {…}, optional, sequence}], visible}}`
- in the code: not used yet

### `POST /orchestrator/graphql`

- seen 6x, status 200, from page `/index.html`
- body: `{operationName, variables: {input: {status, params: {seller_id, status: {…}}}}, query}`
- answer: `{type, error}`
- in the code: not used yet

### `GET /ui-config`

- seen 1x, status 200, from page `/index.html`
- answer: `{abc, adsConfig: {disableCreateCampaign, pfClientUrl, roiBound: {max, min}, topSlotDate}, bbdInsightTitle: {endDate, homepage: {description}, insightPage: {description}, startDate, value}, coupanPenalizationMessage, customerInsightsFeedbackPageModalSize, dhamakaSelectionLeaderBoard: {endDate, leaderboardHeading, startDate}, disableSelfShipOrdersBannerText, disableSelfShipOrdersHoverText, enableCoupanPenalization, enableOnDemandJoyride, enableServiceWorker, feedback: {list: [{discoveryId, featureName, page}], questionOrderMap}, fkOffers: {tags: {tutorial: {defaultTag: {…}, zonalOrderOffers: {…}}}, tutorial: {linkText, youtubeUrl}}, fkiToolKit: {afterOnboardDays}, globalSliderConfig: {bazaar: {header, imageUrl, logo, section: [{…}]}, enable: […], redirectionBanner: {bannerRedirectUrl, imageU`
- in the code: not used yet
<!-- /AUTO:catalogue -->

## Notes (by hand)

- 
