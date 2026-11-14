# Flipkart Seller Hub GraphQL operation inventory

Reviewed 7 Nov 2026 from the existing local `netcap/flipkartcap.json` capture.
Only operation and field names are retained. No authenticated replay was performed.
The captured response shapes were `{type, error}`; successful business response schemas
remain unverified. Query kind describes the request text, not a guarantee of server behavior.
See [the portal guide](flipkart-seller.md) for meanings and follow-up work.

## `POST /napi/graphql`

| Operation | Kind | Seen | Variable fields |
|---|---|---|---|
| `Dashboard_getSelfServeBanners` | query | 3 | `{pageName}` |
| `FetchUniversalSearchConfig` | query | 6 | `{}` |
| `GetAllEInvoiceStatesStatus` | query | 3 | `{sellerId}` |
| `GetBusinessSummaryImpressions` | query | 3 | `{time_interval: […]}` |
| `GetBusinessSummarySalesUnits` | query | 3 | `{fields: […], time_interval: […]}` |
| `GetEarningsSummary` | query | 1 | `{month}` |
| `GetEmptySearchSuggestions` | query | 1 | `{seller_id}` |
| `GetFeatureLaunches` | query | 3 | `{platform}` |
| `GetGSTINsStatus` | query | 6 | `{}` |
| `GetHomepageKpisMetaData` | query | 5 | `{}` |
| `GetInsightBuckets` | query | 3 | `{viewId, searchFilters: {filter_by: [{filter_type, field_name, values: […]}], order_by: […], group_by: [{grouping_name, field_name, sort_order}]}, insightViewId, insightSearchFilters: {filter_by: [{filter_type, field_name, values: […]}], order_by: […], group_by: […]}, insightPagination: {page_number, page_size}}` |
| `GetLargeSellers` | query | 2 | `{}` |
| `GetMilestoneBanner` | query | 3 | `{platform}` |
| `GetPaymentKpiMeta` | query | 5 | `{tier}` |
| `GetPaymentsUIConfig` | query | 1 | `{}` |
| `GetPromotionsConfig` | query | 3 | `{bucket}` |
| `GetSellerBannerDetails` | query | 6 | `{sellerId, version}` |
| `GetUpcomingPaymentsV3` | query | 1 | `{}` |
| `GoogleAds_getAllCampaigns` | query | 3 | `{}` |
| `HomePage_GetSellerState` | query | 6 | `{}` |
| `HomepageDegrowthKpi` | query | 3 | `{current: {view_name, filters: [{field_name, filter_type, range_from, range_to}], sort: […], metrics: [{metric_name, metric_field, metric_type}], derived_metrics: […], aggregate_by, interval, pivot: […], pagination: {page_number, page_size}}, previous: {view_name, filters: [{field_name, filter_type, range_from, range_to}], sort: […], metrics: [{metric_name, metric_field, metric_type}], derived_metrics: […], aggregate_by, interval, pivot: […], pagination: {page_number, page_size}}}` |
| `HomepageDegrowthListingCount` | query | 3 | `{payload: {filters: [{field_name, filter_type, range_from, range_to}], aggregate_by, interval, pagination: {page_number, page_size}, view_name, sort: [{field_name, order}], metrics: [{metric_name, metric_field, metric_type}], derived_metrics: [{metric_name, operator, derived_metrics: [{…}]}], pivot: […]}}` |
| `HomepageDegrowthMinMax` | query | 3 | `{minMaxArgs: {view_name, interval}}` |
| `HomepageDegrowthStatus` | query | 3 | `{status: {view_name, filters: [{field_name, filter_type, range_from, range_to}], sort: […], metrics: [{metric_name, metric_field, metric_type}], derived_metrics: […], aggregate_by, interval, pivot: […], pagination: {page_number, page_size}}}` |
| `Homepage_getMetadata` | query | 3 | `{}` |
| `Homepage_getWidget` | query | 3 | `{widgetId}` |
| `Lqs_getLqsAggRecos` | query | 3 | `{}` |
| `Metrics_fetchGoogleAdsWidgetsConfig` | query | 3 | `{widgetConfigKey}` |
| `PAGES_SUMMARY` | query | 2 | `{}` |
| `Pop_up_Notifications` | query | 6 | `{bucketName, type}` |
| `Promotions_getPromotionsCohorts` | query | 3 | `{}` |
| `ReturnsCount` | query | 5 | `{filter: {return_status: […], shipment_status: […], shipment_types: […], out_for_delivery: {from_date, to_date}}}` |
| `Selection_getGmvLoss` | query | 3 | `{}` |
| `Selection_getStockWidget` | query | 6 | `{filter_by: [{filter_type, field_name, values: […]}]} / {filter_by: […]}` |
| `SellerCopilotGetSummaries` | query | 2 | `{summaryName}` |
| `TransactionPage_getSKUList` | query | 1 | `{tab_name, sub_tab_name, token, size, start_date, end_date, settlement_status}` |
| `TransactionPage_getSKuImage` | query | 4 | `{listingId}` |
| `TransactionPage_getTableFilters` | query | 1 | `{tabName, subTabName, source}` |
| `TransactionPage_getTransactionsHeaderStrip` | query | 1 | `{tabName, subTabName, param, startDate, endDate, filters: {}, settlementStatus, viewType, sort: [{field, direction}]}` |
| `TransactionPage_getTransactionsSubTabs` | query | 1 | `{tabName, param, startDate, endDate, settlementStatus, viewType, sort: [{field, direction}]}` |
| `TransactionPage_getTransactionsTableData` | query | 1 | `{tabName, subTabName, param, startDate, endDate, token, size, filters: {}, settlementStatus, viewType, sort: [{field, direction}]}` |
| `getAddressStatus` | query | 6 | `{locationType}` |
| `getFlipkartAdsWidgetMeta` | query | 2 | `{screen}` |
| `getSchema` | query | 1 | `{pageName, embedded: […]}` |
| `getSellerAccountDetails` | query | 6 | `{}` |
| `promotions_getPromotionsTags` | query | 3 | `{context}` |
| `sellerStories` | query | 3 | `{event}` |

## `POST /orchestrator/graphql`

| Operation | Kind | Seen | Variable fields |
|---|---|---|---|
| `GetPaymentOrderSearchOrchestrator` | query | 1 | `{input: {fromDate, toDate, sort: [{field, direction}], viewType}}` |
| `GetStateCount` | query | 5 | `{input: {status, params: {seller_id, status: {picked_up, dispatched, shipped}}}}` |
