# API calls seen on `seller.flipkart.com`

What each call is for, and what is safe to do with it, is in
the portal's page in `docs/knowledge/`. Calls that change something (POST / PUT that
save, approve, raise or push) are never made by the agent without the owner's approval.

<!-- AUTO:catalogue -->
Generated 14 Nov 2026 by `scripts/knowledge/learn_netcap.py` from fl listing file download price update .json, fl rate cart.json, flipkartcap.json. Names only, no values.

### `GET /fed-ads/navbar/seller`

- seen 13x, status 200, from page `/index.html`
- query: `sellerId`
- answer: `{success, data: [{toShow, label, haveTag, tagProps: {tagStyle, tagText}, id, subMenuItems: [{…}]}]}`
- in the code: not used yet

### `GET /getExperimentVariant`

- seen 5x, status 200, from page `/index.html`
- query: `expName`, `fallbackValue`, `parameter`
- in the code: not used yet

### `GET /getFeaturesForSeller`

- seen 9x, status 200, from page `/index.html`
- answer: `{isWebView, sellerType, chatStatus, enableAlerts, sellerId, sellerDetails: {age, sellerId, status, emailId, contacts: [{name, mobileNumber, contactType, email, sellerId}], displayName, city, pincode, phoneNumber, sellerName, newStatus, tnsBlacklisted, tier: {support}}, csrfToken, allLinksEnabled, featureConfig, redirectState, sellerIdQuery, feature: {reports, singleProductListing, orderManagement}, isDcsCallFailed, isOnBehalf, onBehalfEmail, onBehalfHomePage, enableDropShipment, enableGamificationFlow, isDropShipmentEnabled, isMPSSeller, autoInvoicing, googleAnalyticsId, fbfEnabled, enablePayments, enableOldReturns, enableRTM, enableStaticHomepage, globalConfigStr: {googleAnalyticsId, kissmetricsId, gaUid}, chatCategory, chatUrl, ssChannelName, onboardingDownTime, gaLabelPrefix, ssContactN`
- in the code: `flipkart.py`

### `GET /index.html`

- seen 8x, status ?, from page `/index.html`
- body: `{sku_id, listing_status, mrp, esp, service_profile, procurement_type, shipping_days, stock_size, shipping_provider, local_shipping_fee_from_buyer, zonal_shipping_fee_from_buyer, national_shipping_fee_from_buyer, length_p0, breadth_p0, height_p0, weight_p0, hsn, luxury_cess, tax_code, country_of_origin, manufacturer_details, packer_details}`
- in the code: `flipkart.py`

### `GET /napi/createProductV2/v1/fetch-variant-definition`

- seen 4x, status 200, from page `/index.html`
- query: `vertical`
- answer: `{result: {sellerExposed, fixedAttr: […], distinctAttr: […], groupAttr, groupingAttr: […], variants: {size: {variantAttr: […], fixedAttr: […], distinctAttr: […], imageChange}, color_code: {variantAttr: […], fixedAttr: […], distinctAttr: […], imageChange}}}}`
- in the code: not used yet

### `GET /napi/darwin/finalTier`

- seen 7x, status 200, from page `/index.html`
- answer: `{tier, tierChangeInfo, tieredOn, nextTierDate, tieredFrom, tierEffectiveFrom, breaches: {value, tier, benchmark: {gold, diamond, silver, bronze}}, cancellation: {value, tier, benchmark: {gold, diamond, silver, bronze}}, revenue: {value, tier, benchmark: {platinum, diamond, gold, silver, bronze, wood}}, units: {value, tier, benchmark: {platinum, diamond, gold, silver, bronze, wood}}, returns: {value, tier, benchmark: {platinum, diamond, gold, silver, bronze, wood}}, productRatings: {value, tier, benchmark: {platinum, diamond, gold, silver, bronze, wood}}}`
- in the code: `flipkart.py`

### `GET /napi/edit-product/is-fsn-owner`

- seen 2x, status 200, from page `/index.html`
- query: `productId`
- answer: `{isOwner}`
- in the code: not used yet

### `POST /napi/fdp/batch-events`

- seen 29x, status 200, from page `/index.html`
- query: `sellerId`
- body: `{data: {seller_dashboard_performance: [{schemaVersion, eventTime, eventId, updatedAt, data: {…}}]}, namespace, eventName, sellerId}`
- answer: `{status, traceId}`
- in the code: not used yet

### `GET /napi/fkgrowthcapital/es-discovery`

- seen 3x, status 200, from page `/index.html`
- query: `loanType`, `sellerId`
- answer: `{result: {esOffer: {}}}`
- in the code: not used yet

### `GET /napi/fkgrowthcapital/getOffers`

- seen 3x, status 200, from page `/index.html`
- query: `format`
- in the code: not used yet

### `GET /napi/get-locations`

- seen 7x, status 200, from page `/index.html`
- query: `capabilities`, `include`, `locationType`
- answer: `{result: {multiLocationList: [{value, name, locationId, locationType, locationName, locationDesc, entityId, state, capabilities: [{…}], rtdCutOff: […]}]}}`
- in the code: not used yet

### `GET /napi/get-notifications-count`

- seen 10x, status 200, from page `/index.html`
- query: `mode`, `notificationStatus`, `priority[]`, `sellerId`
- answer: `{request: {mode, actorExternalId, actorType, status: […], notificationRead, actionTaken, priority: […], priorityBelow, priorityAbove, urgencyBelow, urgencyAbove, domains: […], regions: […], startDate, endDate}, count}`
- in the code: not used yet

### `GET /napi/getSellerStoriesDetails`

- seen 2x, status 200, from page `/index.html`
- answer: `{data: {seller_id, fact_date, data: {impressions_growth, orders_growth, Unnamed: 6, bbd_impressions, static, bbd_orders}}}`
- in the code: not used yet

### `POST /napi/graphql`

- seen 537x, status 200, from page `/`, `/index.html`
- body: `{operationName, variables: {bucketName, type}, query}`
- answer: `{type, error}`
- in the code: `flipkart.py`

### `POST /napi/listing/conversion-insights`

- seen 15x, status 200, from page `/index.html`
- body: `{filter_by: [{filter_type, field_name, values: […]}], include_attrs: […], page_size}`
- answer: `{{id}: {recommended_stock, ppv, potential_loss, units_7_days, listing_drr, group_id, size_variant_count}}`
- in the code: not used yet

### `POST /napi/listing/create-update-listings`

- seen 2x, status 200, from page `/index.html`
- query: `inventoryUpdateSource`
- body: `{sellerId, bulkRequests: [{attributeValues: {sku_id: [{…}], listing_status: [{…}], mrp: [{…}], esp: [{…}], service_profile: [{…}], procurement_type: [{…}], shipping_days: [{…}], shipping_provider: [{…}], local_shipping_fee_from_buyer: [{…}], zonal_shipping_fee_from_buyer: [{…}], national_shipping_fee_from_buyer: [{…}], hsn: [{…}], tax_code: [{…}], country_of_origin: [{…}], manufacturer_details: [{…}], packer_details: [{…}], flipkart_selling_price: [{…}]}, listingId, packages: [{…}], locations: [{…}], context: {ignore_warnings}}]}`
- answer: `{result: {status, bulkResponse: [{listingID, skuID, sellerID, productID, status, globalErrors: […], attributeErrors: {…}}]}}`
- in the code: not used yet

### `POST /napi/listing/enqueueDownload`

- seen 2x, status 200, from page `/index.html`
- body: `{state, refiners: {search_text: [{exactValue: {…}, valueType}], internal_state: [{exactValue: {…}, valueType}]}, verticalGroups: {}}`
- answer: `{}`
- in the code: not used yet

### `GET /napi/listing/entityDefinition`

- seen 4x, status 200, from page `/index.html`
- query: `client_id`, `context`, `entity_type`, `fsn`, `seller_id`, `version`, `vertical`
- answer: `{entityDefinition: [{attributeDisplayName, attributeName, attributeType, attributeValueType, isEnum, allowedValues: […], attributeDescription, attributeMaxValue, attributePriority, websiteSectionName, defaultQualifier, attributeOrder, qualifierAllowedValues: […], qualifierDisplayValueMap: {MONTHS}}]}`
- in the code: not used yet

### `POST /napi/listing/fetch-recommendations-filter-count`

- seen 16x, status 200, from page `/index.html`
- body: `{search_text, search_filters: {stock_recommendation, qc_recommendation: […], listing_tier, minoq_recommendation, multipacks_recommendation, internal_state, shopsy_recommendation}, enableOOSTopListings}`
- answer: `{filter_count_map: {listing_tier, shopsy_recommendation, minoq_recommendation, multipacks_recommendation, qc_recommendation, stock_recommendation}}`
- in the code: not used yet

### `GET /napi/listing/fetch-seller-potential-sales-loss`

- seen 7x, status 200, from page `/index.html`
- query: `internal_state`, `reason_code`
- answer: `{seller_potential_loss: {gmv_loss, unit_loss}}`
- in the code: not used yet

### `POST /napi/listing/filtered-inventory-info`

- seen 4x, status 200, from page `/index.html`
- body: `{listing_id, profiles: […]}`
- answer: `[{quantity, reserved, locationId, state, name, pincode}]`
- in the code: not used yet

### `GET /napi/listing/get-listings-info-by-id`

- seen 7x, status 200, from page `/index.html`
- query: `listingId`, `sellerId`
- answer: `{{id}: {listingId, productId, attributeData: {marketplace_id: [{…}], listing_tier: [{…}], service_profile: [{…}], esp: [{…}], is_poor_quality: [{…}], ssp: [{…}], shipping_days: [{…}], product_id: [{…}], listing_status: [{…}], last_modified: [{…}], seller_id: [{…}], mpd: [{…}], national_shipping_fee_from_buyer: [{…}], mpc: [{…}], importer_details: [{…}], seller_listing_state: [{…}], country_of_origin: [{…}], sku_id: [{…}], seller_price: [{…}], fk_release_date: [{…}], seller_tier_value: [{…}], stock_size: [{…}], internal_state: [{…}], seller_tier: [{…}], procurement_type: [{…}], hsn: [{…}], shipping_provider: [{…}], listing_id: [{…}], manufacturer_details: [{…}], cls_id: [{…}], vertical: [{…}], part_payment_enabled: [{…}], is_cod_available: [{…}], listing_version: [{…}], local_shipping_fee_f`
- in the code: not used yet

### `POST /napi/listing/get-listings-tier`

- seen 15x, status 200, from page `/index.html`
- body: `{listing_details: [{listing_id, service_profile}]}`
- answer: `{response: [{listing_id, service_profile, listing_tier}]}`
- in the code: not used yet

### `GET /napi/listing/get-size-chart-categories`

- seen 5x, status 200, from page `/index.html`
- answer: `[…]`
- in the code: not used yet

### `POST /napi/listing/get-stock-reco-for-listing`

- seen 2x, status 200, from page `/index.html`
- body: `{filter_by: [{filter_type, field_name, values: […]}], include_attrs: […], group_by: […], page_number, page_size}`
- answer: `{{id}: {recommendedStock, doh, listingDrr}}`
- in the code: not used yet

### `GET /napi/listing/getSellerMPAffinityFlag`

- seen 8x, status 500, from page `/index.html`
- query: `profile_ids`, `sellerId`, `signal_names`
- answer: `{error: {message}}`
- in the code: not used yet

### `GET /napi/listing/lag`

- seen 4x, status 200, from page `/index.html`
- answer: `{msg}`
- in the code: not used yet

### `POST /napi/listing/listing-price-recommendation`

- seen 2x, status 200, from page `/index.html`
- body: `{request: {filter_by: [{filter_type, field_name, values: […]}], order_by: […], group_by: […], page_number, page_size, x-feature-id}, viewId}`
- answer: `{data: {insight_type, seller_id, aggregations: […], insights_data: {}, meta_data: {}}}`
- in the code: not used yet

### `POST /napi/listing/listings-price-recommendation`

- seen 15x, status 200, from page `/index.html`
- body: `{filter_by: [{filter_type, field_name, values: […]}], include_attrs: […], page_size, x-feature-id}`
- answer: `{{id}: {pricing_strategy, recommended_price, recommended_price_min, recommended_price_max, insight_sub_type, insight_id, value_tags: […], variant_type, group_id, flipkart_settlement_price, recommended_settlement}, LSTAZTGWGYFUKEPAJUMCGQLY5: {pricing_strategy, recommended_price, recommended_price_min, recommended_price_max, insight_sub_type, insight_id, value_tags: […], variant_type, group_id, flipkart_settlement_price, recommended_settlement}}`
- in the code: not used yet

### `GET /napi/listing/listingsCountForStates`

- seen 6x, status 200, from page `/index.html`
- answer: `{listings_count: {INACTIVATED_BY_FLIPKART, ACTIVE, READY_FOR_ACTIVATION, ARCHIVED, INACTIVE}}`
- in the code: not used yet

### `POST /napi/listing/listingsDataForStates`

- seen 49x, status 200, from page `/index.html`
- body: `{search_text, search_filters: {internal_state}, column: {sort: {column_name, sort_by}, pagination: {batch_no, batch_size}}}`
- answer: `{count, listing_data_response: [{sku_id, seller_id, listing_id, vertical, product_id, fk_release_date, vertical_display_name, service_profile, internal_state, listing_tier, shipping_days, procurement_type, ssp, esp, mrp, reason_for_deactivation: […], reason_for_archival: […], packages: {{id}: {…}}, hsn, shipping_provider, local_shipping_fee_from_buyer, zonal_shipping_fee_from_buyer, national_shipping_fee_from_buyer, subsidized_shipping, potential_rfa_loss, potential_rfa_unit, minimum_order_quantity, potential_tag, brand, imageUrl, zulu_chart_status, url, title, grade, visibilityStatePostQc, is_discoverable}]}`
- in the code: `flipkart.py`

### `POST /napi/listing/listingsFilterValues`

- seen 24x, status 200, from page `/index.html`
- body: `{internal_state, requested_filter, search_filters: {}}`
- answer: `{search_filter_value: {vertical: {tree: {Clothing: {…}, Shopsy: {…}}}}}`
- in the code: not used yet

### `GET /napi/listing/listingsStateViewTemplate`

- seen 5x, status 200, from page `/index.html`
- query: `context`, `search_filter`
- answer: `{preferred_view, views: [{name, id, contents: [{…}]}], search_filters: [{dashboard_attributes, display_name, type}], columns: [{dashboard_attributes, display_name, column_type}]}`
- in the code: not used yet

### `POST /napi/listing/listingsStockCount`

- seen 15x, status 200, from page `/index.html`
- body: `[{listing_id, service_profile}]`
- answer: `{{id}: {FBF: [{quantity, locationId}], NON_FBF: [{quantity, reserved, locationId}]}, {id}: {NON_FBF: [{quantity, reserved, locationId}]}, LSTAZTGWGYFUKEPAJUMCGQLY5: {NON_FBF: [{quantity, reserved, locationId}]}, LSTAZTGWGYFAQRACY4XK7WLEN: {NON_FBF: [{quantity, reserved, locationId}]}}`
- in the code: not used yet

### `POST /napi/listing/lqs-grade-details`

- seen 15x, status 200, from page `/index.html`
- body: `{listing_ids: […], fields: […]}`
- answer: `{lqs_grade_details_list: [{listing_id, lqs_grade, banner_text, is_derived_value, ratings_bm, returns_bm, model, vertical_alias, vertical}]}`
- in the code: not used yet

### `POST /napi/listing/lqs-insights-reco-new-bulk`

- seen 5x, status 200, from page `/index.html`
- body: `[{listing_id, vertical}]`
- answer: `{{id}: {listing_id, return_insights: [{reason_sub_reason, reason, description, cta_title, count, action, return_percentage, is_dynamic_text, new_insights}]}, LSTTOPHFVQZHVKRCGQHQNRIWU: {listing_id, return_insights: [{reason_sub_reason, reason, description, cta_title, count, action, return_percentage, is_dynamic_text, new_insights}]}, LSTDREHGYNMHKXHKHB9CJDPX8: {listing_id, return_insights: [{reason_sub_reason, reason, description, cta_title, count, action, return_percentage, is_dynamic_text, new_insights}]}, LSTDREHGYNMMXYYDJV3T8BTXU: {listing_id, return_insights: [{reason_sub_reason, reason, description, cta_title, count, action, return_percentage, is_dynamic_text, new_insights}]}, {id}: {listing_id, return_insights: […]}, LSTDREHGYNMGDFPJSTQGYTVUE: {listing_id, return_insights: [{reason_`
- in the code: not used yet

### `POST /napi/listing/lqs-metrics-impressions`

- seen 15x, status 200, from page `/index.html`
- body: `[{listing_id}]`
- answer: `{metrics: [{listing_id, impressions: {value, tag, text}, buy_now: {value, tag, text}, ml_ratings: {value}, ml_returns: {value}, act_ratings: {value}, act_returns: {value}, hist_returns, hist_ratings, hist_impressions: {refreshDate, value}, hist_buy_now: {refreshDate, value}, hist_lqs_band, ddmm_tag, rating_benchmark, ddmm_benchmark, business_unit, service_profile, delivered_units, lqs_index, fa: {value}}]}`
- in the code: not used yet

### `GET /napi/listing/moq-eligibility`

- seen 12x, status 200, from page `/index.html`
- query: `fsn`, `vertical`
- answer: `{decision_rules: […]}`
- in the code: not used yet

### `GET /napi/listing/mspEnabled`

- seen 10x, status 200, from page `/index.html`
- in the code: not used yet

### `GET /napi/listing/priceUpdateHistory`

- seen 12x, status 200, from page `/index.html`
- query: `attribute`, `id`
- answer: `[{channel, timestamp, new_value, old_value, user_name}]`
- in the code: `flipkart.py`

### `POST /napi/listing/pricing-reco-data`

- seen 16x, status 200, from page `/index.html`
- body: `{filter_by: [{filter_type, field_name, values: […]}], order_by: […], group_by: [{grouping_name, field_name, sort_order, child: {grouping_name, field_name, sort_order}}], page_number, page_size, x-feature-id}`
- answer: `{insight_type, seller_id, aggregations: [{aggregation_name, buckets: [{…}], value}], insights_data: {}, meta_data: {model_meta_data: {competitive_pricing: {description, title, tooltipText}, increase_conversions: {description, title, tooltipText}, value_tags_reco, cart_and_wishlist_products: {description, title, tooltipText}, low_po_price_reco}}}`
- in the code: not used yet

### `GET /napi/listing/pricingInfo`

- seen 15x, status 200, from page `/index.html`
- query: `listingIds`
- answer: `{{id}: {usual_price, final_price, referenceIds}, LSTAZTGWGYFUKEPAJUMCGQLY5: {usual_price, final_price, referenceIds}, LSTAZTGWGYFAQRACY4XK7WLEN: {usual_price, final_price, referenceIds}}`
- in the code: not used yet

### `POST /napi/listing/report/check-report`

- seen 2x, status 200, from page `/index.html`
- body: `{sellerId, report_group_name, report_name, return_reason, selectedRows: […]}`
- answer: `{request_id, downloadLink: {}}`
- in the code: not used yet

### `POST /napi/listing/return-insight-data`

- seen 5x, status 200, from page `/index.html`
- body: `{viewId, reasonFilters: […], pagination: {batch_no, batch_size}, orderBy: [{field_name, order}]}`
- answer: `{response: {zulu: [{entityId, entityVersion, entityType, entitySubType, viewName, viewDefinitionVersion, viewVersion, view: {…}}], insights: [{id, entity_id, tags: […], enriched_attributes: {…}, insight_attributes: {…}, misc_attributes: {…}, impact_attributes: {…}}]}}`
- in the code: not used yet

### `POST /napi/listing/return-reason-filters`

- seen 2x, status 200, from page `/index.html`
- body: `{viewId, reasonFilters: […]}`
- answer: `{insight_type, seller_id, aggregations: […], insights_data: {}, meta_data: {category: […], brand: […]}}`
- in the code: not used yet

### `POST /napi/listing/return-reason-percentage`

- seen 2x, status 200, from page `/index.html`
- body: `{reason, viewNameReturnReasonLevel, viewNameReturnOverallLevel}`
- answer: `{returnPercentage}`
- in the code: not used yet

### `POST /napi/listing/return-reason-updated-time-duration`

- seen 2x, status 200, from page `/index.html`
- body: `{reason: […], viewId}`
- answer: `{response: {startDate, endDate, latestUpdatedTime}}`
- in the code: not used yet

### `POST /napi/listing/return-reco-count-revenue`

- seen 18x, status 200, from page `/index.html`
- body: `{viewId, reasonFilters: […]}`
- answer: `{insight_type, seller_id, aggregations: [{aggregation_name, buckets: [{…}], value}], insights_data: {}, meta_data: {}}`
- in the code: not used yet

### `POST /napi/listing/risk-recommendation-data-count`

- seen 16x, status 200, from page `/index.html`
- body: `{}`
- answer: `{warned, suppressed, deactivated, at_risk}`
- in the code: not used yet

### `GET /napi/listing/stockFileDownloadNUploadHistory`

- seen 13x, status 200, from page `/index.html`
- answer: `{stock_file_response_list: [{file_link, file_operation_type, file_name, error_count, total_count, file_format, uploaded_on, feed_state, error_rows_exists}]}`
- in the code: not used yet

### `GET /napi/listing/stockFileDownloadRequestStatus`

- seen 8x, status 200, from page `/index.html`
- answer: `{sellerId, lastDownloadTimestamp, downloadState, processed_count, totalCount}`
- in the code: not used yet

### `GET /napi/listing/stockFileUploadRequestStatus`

- seen 4x, status 200, from page `/index.html`
- answer: `{HSUI9KTFVJIBS: {feedId, role, feedState, feedCounters: {totalRows, rowsProcessed, rowsSuccessful, newListingCnt, updatedListingCnt, physicalTotalRows, rowsWithErrors, qcPassedRows, qcFailedRows, rowLevelErrors: {}}, feedType, requestId, sellerId, lastModified}}`
- in the code: not used yet

### `POST /napi/listing/updateSellingPrice`

- seen 8x, status 200, from page `/index.html`
- query: `userName`, `warningConfirmed`
- body: `{listingUpdate: {AAY-COORD-CJ-1-N15-M: {product_id, price: {mrp, selling_price, currency, esp}}}, priceRecoUpdate: {}}`
- answer: `{AAY-COORD-CJ-1-N15-M: {status}}`
- in the code: `flipkart.py`

### `GET /napi/metrics/bizReport/downloadReport/{id}`

- seen 5x, status 200, from page `/index.html`
- query: `sellerId`, `token`
- in the code: not used yet

### `POST /napi/metrics/bizReport/getReportsCount`

- seen 29x, status 200, from page `/index.html`
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

- seen 25x, status 200, 500, from page `/index.html`
- body: `{reportGroup, reportName, enable, status, page_size, starting_page}`
- answer: `{error: {headers: {date, content-type, content-length, x-envoy-upstream-service-time, server, x-elb-id, x-elb-app-server}, statusCode, error: {code, message}}}`
- in the code: `flipkart.py`

### `GET /napi/metrics/bizReport/reportCategories`

- seen 9x, status 200, from page `/index.html`
- answer: `[{report_group_id, type, description, feature_flag}]`
- in the code: not used yet

### `GET /napi/metrics/bizReport/reportsNew`

- seen 15x, status 200, from page `/index.html`
- query: `reportGroupName`
- answer: `[{report_group_id, report_id, name, description, detail, version}]`
- in the code: not used yet

### `POST /napi/metrics/bizReport/submitReport`

- seen 6x, status 200, from page `/index.html`
- query: `reportName`
- body: `{from_date, to_date, file_format, type, filters: [{values: […], operator, name}]}`
- answer: `{request_id: {request_id, eta}}`
- in the code: not used yet

### `GET /napi/metrics/darwin/v3/tiering-metrics`

- seen 14x, status 200, from page `/index.html`
- answer: `{metrics_data: {metrics: {customer_experience: {category: {…}}, sales: {category: {…}}, service_quality: {category: {…}}}, from_date, to_date, end_date, evaluation_date, trending_tier, tier_code, is_new_seller, last_boost_date, go_live_date, cancellation_allowance_applied, seller_cancellation_units, dbd_breach_units, dbd_allowance_applied}, benchmarks: {customer_experience: {product_rating: {tiers: {…}, unit}}, sales: {}, service_quality: {rtd_breaches: {tiers: {…}, unit}, cancellations: {tiers: {…}, unit}}}, tier_list: {1, 2, 3, 4}, finalTier: {seller_id, is_new_seller, type, last_approved_date, last_updated_date, start_date, end_date, tier_reason, version_id, category, message, tier_value, tier, tier_name, metadata: {metrics: {customer_experience: {…}, sales: {…}, service_quality: {…}}, `
- in the code: not used yet

### `POST /napi/metrics/search`

- seen 15x, status 200, from page `/index.html`
- body: `{filters: [{field_name, filter_type, range_from, range_to}], metrics: [{metric_name, metric_field, metric_type}], aggregate_by, interval, pivot: […], page_number, page_size}`
- answer: `{seller_id, pivots: […], interval, date_range: {start_date, end_date}, data: [{return_amount, listing_id, return_units, delivered_amount, delivered_units, refund_units, refund_amount, timestamp, listing_spp: […]}], has_exceptional_context}`
- in the code: `flipkart.py`

### `GET /napi/partner-master/v0/ads`

- seen 3x, status 200, from page `/index.html`
- query: `page`, `type`
- answer: `{page, ads_details: [{partner_id, partner_category_id, partner_business_name, partner_logo_url, category_id, category_name, category_logo_url, type, price, banner_url, redirect_url, campaign_id}]}`
- in the code: not used yet

### `GET /napi/payments/fetchBlockStatus`

- seen 3x, status 200, from page `/index.html`
- query: `tier`
- answer: `{payment_expected, message_id, message, payout_cycle_change, payout_cycle_message, payment_failed_message, payment_delayed, payment_failed}`
- in the code: not used yet

### `GET /napi/payments/fetchLastPaymentDetails`

- seen 3x, status 200, from page `/index.html`
- answer: `{bifurcation_summary_list: [{bifurcation_details: {order: {…}, protection_fund: {…}, rewards: {…}, service: {…}, taxation: {…}}, allow_prepaid_drill_down, allow_postpaid_drill_down, id, event, reason, aggr_amount: {prepaid, postpaid, total}, prepaid_detail: {utr_number, settlement_status, bank_account_no, utr_label}, postpaid_detail: {utr_number, settlement_status, bank_account_no, utr_label}}], payments: [{start_date, payment_date, end_date, prepaid, postpaid, total_amount}], total, remaining, payment_time, holiday_reason, sync_date, cached}`
- in the code: not used yet

### `GET /napi/payments/fetchOutstandingPaymentDetails`

- seen 3x, status 200, from page `/index.html`
- answer: `{bifurcation_summary_list: [{bifurcation_details: {order: {…}, protection_fund: {…}, rewards: {…}, service: {…}, taxation: {…}}, allow_prepaid_drill_down, allow_postpaid_drill_down, id, event, reason, aggr_amount: {prepaid, postpaid, total}, prepaid_detail, postpaid_detail}], payments: [{start_date, payment_date, end_date, prepaid, postpaid, total_amount}], total, remaining, payment_time, holiday_reason, sync_date, cached}`
- in the code: not used yet

### `GET /napi/payments/fetchSellerStatement`

- seen 1x, status 200, from page `/index.html`
- query: `settlement_type`
- answer: `{statement_detail: {opening_balance, total_balance, net_balance, total_payment, closing_balance, accumulated_amount, settlement_date, payment_type, payment_type_label, settlement_start_date, settlement_end_date, min_date, max_date, open_balance_as_of_date, close_balance_as_of_date, on_board_date, advice_id, utr_number, is_mismatched, mismatched_amount, fasrequired}, fee_classification: {sales: {total_sales: {credit, debit, net_settlement}, refunds: {credit, debit, net_settlement}, ndd_sdd_amount: {credit, debit, net_settlement}, cancellation_fee: {credit, debit, net_settlement}, offers: {customer_discount_by_seller: {…}, customer_discount_total: {…}, aggregated_amount}, aggregated_amount}, spf_payout: {credit, debit, net_settlement}, services: {fee_groups: [{…}], aggregated_amount}, mp_fee`
- in the code: not used yet

### `GET /napi/returns/downloadBulkProofOfPickup`

- seen 2x, status 200, from page `/index.html`
- query: `date`, `locationId`, `sellerId`, `vendor_name`
- in the code: not used yet

### `GET /napi/riddler/fetchAssignedQuestionsCount`

- seen 25x, status 200, from page `/index.html`
- query: `sellerId`
- answer: `{unansweredCount, bookmarkCount}`
- in the code: not used yet

### `GET /napi/seller-capability/fetch-capability`

- seen 20x, status 200, from page `/index.html`
- query: `capabilityName`
- answer: `{CAP_SELLER_LOCKIN}`
- in the code: not used yet

### `GET /napi/seller-products/bulk-edit/download-history`

- seen 15x, status 200, from page `/index.html`
- answer: `{bulkEditFeedDownloadHistoryList: [{requestId, fileName, fileURL, completedOn, status}]}`
- in the code: not used yet

### `GET /napi/sellerBuyerCommunications/isSellerEnabled`

- seen 19x, status 200, from page `/index.html`
- query: `sellerId`
- answer: `{result: {request: {actor_id, actor_type}, enabled, argos_id, chat_listing_scope, perf_policy, multi_agent}}`
- in the code: not used yet

### `GET /napi/srm/getQuestionnaireByFeature`

- seen 16x, status 200, from page `/index.html`
- query: `featureName`
- answer: `{data: {createdAt, updatedAt, createdBy, updatedBy, discoveryId, id, description, questionMappings: [{id, question: {…}, optional, sequence}], visible}}`
- in the code: not used yet

### `GET /napi/ugc/fetchAnsweredQuestionsForFSN`

- seen 2x, status 200, from page `/index.html`
- query: `pageNo`, `pageSize`, `productId`
- answer: `{qnaSummary, questionDetails: […], hasMore}`
- in the code: not used yet

### `GET /napi/ugc/fetchUnansweredQuestionsForFSN`

- seen 4x, status 200, from page `/index.html`
- query: `pageNo`, `pageSize`, `productId`
- answer: `{count, unansweredQuestionDetailList: [{questionId, questionText, modelScore, createdAt}], hasMore}`
- in the code: not used yet

### `POST /orchestrator/graphql`

- seen 30x, status 200, from page `/index.html`
- body: `{operationName, variables: {input: {status, params: {seller_id, status: {…}}}}, query}`
- answer: `{type, error}`
- in the code: `flipkart.py`

### `POST /snoopyIngestion`

- seen 93x, status 204, from page `/index.html`
- body: `{event: {channel, org, action, entity: {name, child: {name, child: {…}}}, data_category, value, page_load_id, event_no, flow_id, source, medium, term, campaign}, type}`
- in the code: not used yet

### `GET /ui-config`

- seen 7x, status 200, from page `/index.html`
- answer: `{abc, adsConfig: {disableCreateCampaign, pfClientUrl, roiBound: {max, min}, topSlotDate}, bbdInsightTitle: {endDate, homepage: {description}, insightPage: {description}, startDate, value}, coupanPenalizationMessage, customerInsightsFeedbackPageModalSize, dhamakaSelectionLeaderBoard: {endDate, leaderboardHeading, startDate}, disableSelfShipOrdersBannerText, disableSelfShipOrdersHoverText, enableCoupanPenalization, enableOnDemandJoyride, enableServiceWorker, feedback: {list: [{discoveryId, featureName, page}], questionOrderMap}, fkOffers: {tags: {tutorial: {defaultTag: {…}, zonalOrderOffers: {…}}}, tutorial: {linkText, youtubeUrl}}, fkiToolKit: {afterOnboardDays}, globalSliderConfig: {bazaar: {header, imageUrl, logo, section: [{…}]}, enable: […], redirectionBanner: {bannerRedirectUrl, imageU`
- in the code: not used yet
<!-- /AUTO:catalogue -->

## Notes (by hand)

- 
