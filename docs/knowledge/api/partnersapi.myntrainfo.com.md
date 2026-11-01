# API calls seen on `partnersapi.myntrainfo.com`

What each call is for, and what is safe to do with it, is in
the portal's page in `docs/knowledge/`. Calls that change something (POST / PUT that
save, approve, raise or push) are never made by the agent without the owner's approval.

<!-- AUTO:catalogue -->
Generated 01 Nov 2026 by `scripts/knowledge/learn_netcap.py` from MYNTRA PRICE UPDATE.json, MYNTRA TICKET RAISE .json, Myntra OTP Cap.json. Names only, no values.

### `GET /api/boot/partners`

- seen 5x, status 200, from page `/`, `/Dashboard`, `/Reports/seller-reports`
- query: `reloaded`
- answer: `{__version, device: {isMobile, isDesktop}, baseUrl, config: {cookie: {prefix, domain}, qcEngine: {security: {application: {…}, resource: {…}, teamTypes: [{…}]}}, services: {spf: {root, path}, voicePlatform: {root, path}, kuber: {root, path}, mlp: {root, path}, accio: {root, path}, gauntlet: {root, path}, settlementService: {root, path}, pricingEngine: {root, path, auth}, adwiser: {root, path}, mintAdvantage: {root, path}, mintAdventureGrpc: {root}, agreements: {root, path}, stockv2: {root, path, auth}, erpims: {root, path, auth}, irisAgent: {root, path, auth}, ugc: {root, path}, ratings: {root, path}, cmscatalogservice: {root, path, auth}, audit: {path, auth, root}, worms: {root, path, auth}, orderIntegration: {root, path}, mwsAirflow: {root, path}, ims: {path, auth, root}, atp: {path, aut`
- in the code: `myntra.py`

### `GET /api/file-manager/getUploadToken/spfJob`

- seen 2x, status 200, from page `/SPF`
- query: `fileNames`
- answer: `{{id}: {sasUrl, fileNameWithPath}}`
- in the code: `myntra.py`

### `GET /api/location/otc`

- seen 4x, status 200, from page `/OTC`
- query: `trip`, `warehouse`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, warehouseId, tripType, otcDetails: [{status: {statusCode, statusMessage, statusType, totalCount}, courierCode, otc}]}`
- in the code: `pipeline.py`, `myntra.py`

### `GET /api/partners/leftnav/fbm-status`

- seen 4x, status 200, from page `/Dashboard`, `/Reports/seller-reports`
- answer: `{isFbm}`
- in the code: not used yet

### `GET /api/partners/notifications/announcements`

- seen 3x, status 200, from page `/Dashboard`
- query: `fetchSize`, `start`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data: [{id, recipients: […], clientType, status, state, priority, activationDate, expiryDate, misc: {content, groupNames, numberOfDays, title}, customData: {priority}, refId, createdOn, lastModifiedOn, createdBy, lastModifiedBy, isPWAEnabled}]}`
- in the code: not used yet

### `GET /api/partners/notifications/tasks`

- seen 12x, status 200, from page `/Dashboard`, `/Reports/seller-reports`
- query: `fetchSize`, `recipient`, `type`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data}`
- in the code: not used yet

### `GET /api/partners/report/summary/next-payment`

- seen 6x, status 200, from page `/Dashboard`
- answer: `{status: {statusCode, statusMessage, statusType}, data: {paymentDate, prepaidAmount, postpaidAmount, totalAmount}}`
- in the code: not used yet

### `GET /api/partners/report/summary/outstanding-payment`

- seen 3x, status 200, from page `/Dashboard`
- answer: `{status: {statusCode, statusMessage, statusType}, data: {prepaidAmount, postpaidAmount, totalAmount, updated_at, detailsLink}}`
- in the code: not used yet

### `GET /api/partners/report/summary/payment-history`

- seen 3x, status 200, from page `/Dashboard`
- query: `fromDate`, `pageNo`, `pageSize`, `toDate`, `type`
- answer: `{status: {statusCode, statusMessage, statusType}, data: {totalElements, totalPages, totalAmount, prepaidAmount, postpaidAmount, payments: [{paymentMethod, utrNumber, paymentDate, yearMonth, amount, utrDetailsLink, adviceId}]}}`
- in the code: `myntra.py`

### `GET /api/partners/seller-activation/seller-achievements`

- seen 7x, status 200, from page `/Dashboard`, `/Reports/seller-reports`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: […]}`
- in the code: not used yet

### `GET /api/partners/seller-performance/contract-tier`

- seen 3x, status 200, from page `/Dashboard`
- answer: `{status: {statusType, statusMessage, statusCode}, data: [{term: {id, entityType, type, contractId, entityId, startedOn, endedOn, status, referenceId, tag, comments, remarks, createdBy, transitions, createdAt, updatedAt, autoRenewalEnabled, tier, autoRenewalCycle, model}, exception}]}`
- in the code: not used yet

### `GET /api/partners/seller-performance/dashboard`

- seen 3x, status 200, from page `/Dashboard`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: [{evalQuarter, dataInsertTime, metricScores: [{…}], totalStars, finalSellerTier, previousEvalQuarter, previousRevenue, previousUnits, previousPaymentAmount, previousTotalStars, previousO2pMetric, previousCancelMetric, previousBreachMetric, previousRuMetric, previousRatingMetric, previousFreshnessMetric, previousScrMetric, freshnessThresholdGold, thresholdScrGold, thresholdScrSilver, previousDataInsertTime}]}`
- in the code: not used yet

### `GET /api/partners/seller-performance/tier-cutoff`

- seen 3x, status 200, from page `/Dashboard`
- answer: `[{term: {id, entityType, type, contractId, entityId, startedOn, endedOn, status, referenceId, tag, comments, remarks, createdBy, transitions, createdAt, updatedAt, tierCutOff: [{…}]}, exception}]`
- in the code: not used yet

### `GET /api/partners/sellerreports/all-new`

- seen 1x, status 200, from page `/Reports/seller-reports`
- query: `month`, `year`
- answer: `{status: {statusType, statusCode, statusMessage}, data: {OTHERS: [{displayName, reportPath, reportName, appName, subType}]}}`
- in the code: not used yet

### `GET /api/partners/vendorService/v3/partnerContactAddress/partner/addressType/SHIPPING`

- seen 2x, status 200, from page `/OTC`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data: [{id, createdBy, createdOn, lastModifiedOn, version, address1, address2, city, state, stateCode, pinCode, country, countryCode, partnerId, enabled, addressType, partnerType, warehouseId, uuid, isInternational, parentUUID, partnerWarehouseCode}]}`
- in the code: not used yet

### `GET /api/partners/vms/v3/partner`

- seen 3x, status 200, from page `/Dashboard`
- query: `ids`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, partnerEntries: [{id, createdBy, createdOn, lastModifiedOn, version, name, barcode, displayName, enabled, description, status, entityType, partnerType, msme, uuid, lastModifiedBy, remarks, partnerContactPersons: [{…}]}]}`
- in the code: not used yet

### `GET /api/pricing/configurations/exists`

- seen 1x, status 200, from page `/Pricing/recommendations`
- query: `usecase`, `value`
- answer: `{result: {usecase, value, exists}, statusCode, statusMessage, statusType}`
- in the code: not used yet

### `POST /api/pricing/fetchRecommendationsFilter`

- seen 1x, status 200, from page `/Pricing/recommendations`
- body: `{pageIndex, pageSize, tab}`
- answer: `{data: [{id, styleId, sellerId, mrp, tpType, tpTypeLabel, bagConfigId, sourceType, styleMeta: {brandName, articleType, imageUrl, listViewName}, createdOn, updatedOn, currentListingPriceBreakdown: {sellingPrice, sellingPriceExcludeGtaFees, settlementAmount, gtaFee, pickAndPackFee, commissionAmount, commissionPercentage, fixedFee, incentiveAmount, calculatedTcsAmount, calculatedTdsAmount, collectionCostAmount, maxCollectionCostAmount, incentiveCommissionPercentage, incentiveFixedCost, logisticsGstRate, anchorSettlement, anchorPrice, tolerance}, optInStatus, sellerAction, currentSettlementAmount, currentSellingPrice, recommendedSettlementAmount, recommendedSellingPriceValue, dailyAvgUnitsPostOptIn, salesPostOptIn, optInDate, rateCardValidityStart, rateCardValidityEnd, recommendedPriceBreakdow`
- in the code: not used yet

### `GET /api/pricing/fetchSellerTerms`

- seen 1x, status 200, from page `/Pricing/recommendations`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data: [{id, createdBy, createdOn, lastModifiedOn, version, entityId, entityType, category, key, value, enabled, uuid, parentUUID}]}`
- in the code: not used yet

### `POST /api/pricing/filterDos/{id}`

- seen 3x, status 200, from page `/Pricing/manage`
- body: `{doTypeFilter, pageIndex, pageSize, sourceTypeFilters: […], discountSource, expiredDOFilter, doIds: […], minStartDate, maxStartDate, statusFilters: […]}`
- answer: `{discountOverrideDTOs: [{createdBy, createdOn, description, discountFundingType, discountOverrideSellerDTO: {sellerName, sellerPartnerEmail, sellerPartnerId, sellerPartnerType}, discountSource, discountValueType, doStatusOnPartnerPortal, doType, endDate, id, masterDiscountOverrideId, maxDiscountValue, merge, minDiscountValue, name, newOfferTypeRequired, offerType, sellerPartnerId, srcType, startDate, status, timerRequired, totalStyles, updatedBy, updatedOn}], count}`
- in the code: not used yet

### `POST /api/pricing/jobtracker/job/filterjobs`

- seen 2x, status 200, from page `/Pricing/recommendations`
- body: `{pageIndex, pageSize, types: […]}`
- answer: `{data: […], status: {statusCode, statusMessage, statusType, totalCount}}`
- in the code: not used yet

### `GET /api/pricing/jobtracker/job/{id}`

- seen 6x, status 200, from page `/Pricing/recommendations`
- answer: `{data: [{id, completedStepCount, createdBy, createdOn, errorFileName, expiryTime, inputFileName, lastModifiedOn, qualifier, remark, requestJsonEntry, resultUrl, status, successFileName, terminationRoutingKey, totalStepCount, type, unityS3Url}], status: {statusCode, statusMessage, statusType, totalCount}}`
- in the code: not used yet

### `PUT /api/pricing/sellerDiscountAction/{id}`

- seen 2x, status 200, from page `/Pricing/manage`
- query: `honourTDExclusion`, `honourTDRange`
- body: `{discountOverrideIDStatuses: [{id, status, message}]}`
- answer: `{code, message, statusCode}`
- in the code: not used yet

### `PUT /api/pricing/settlement-pricing/approve/CALCULATE_SELLING_PRICE`

- seen 2x, status 200, from page `/Pricing/recommendations`
- body: `{styleId, sellingPrice, mrp, startTime, endTime, userSegment, settlementAmount, codbBreakdown: {gtaFee, fixedFee, pickAndPackFee, commissionAmount, commissionPercentage, collectionCostAmount}, articleTypeName}`
- answer: `{result: {createdBy, jobId, jobRemarks, jobStatus}, statusCode, statusMessage, statusType}`
- in the code: not used yet

### `POST /api/pricing/settlement-pricing/calculate/CALCULATE_SELLING_PRICE`

- seen 1x, status 200, from page `/Pricing/recommendations`
- body: `{styleId, settlementAmount, brand, article, articleTypeName, gender, masterCategory, articleLevel, mrp, startTime, endTime}`
- answer: `{result: {styleId, sellerId, sellerIds, imageUrl, description, brandName, brand, article, articleTypeName, gender, masterCategory, articleLevel, mrp, mrpBreakdown, recommendedPriceBreakdownDual, fulfillmentBreakdowns: {PPMP: {sellingPrice, sellingPriceExcludeGtaFees, settlementAmount, gtaFee, pickAndPackFee, commissionAmount, commissionPercentage, fixedFee, incentiveAmount, calculatedTcsAmount, calculatedTdsAmount, collectionCostAmount, maxCollectionCostAmount, incentiveCommissionPercentage, incentiveFixedCost, logisticsGstRate, anchorSettlement, anchorPrice, tolerance}}, supportedBreakdownTypes: […], rateCardType}, statusCode, statusMessage, statusType}`
- in the code: not used yet

### `POST /api/pricing/settlement-pricing/view`

- seen 1x, status 200, from page `/Pricing/recommendations`
- body: `{styleId}`
- answer: `{result: {styleId, sellerId, sellerIds, imageUrl, description, brandName, brand, article, articleTypeName, gender, masterCategory, articleLevel, mrp, mrpBreakdown: {sellingPrice, sellingPriceExcludeGtaFees, settlementAmount, gtaFee, pickAndPackFee, commissionAmount, commissionPercentage, fixedFee, incentiveAmount, calculatedTcsAmount, calculatedTdsAmount, collectionCostAmount, maxCollectionCostAmount, incentiveCommissionPercentage, incentiveFixedCost, logisticsGstRate, anchorSettlement, anchorPrice, tolerance}, recommendedPriceBreakdownDual, fulfillmentBreakdowns, supportedBreakdownTypes: […], rateCardType}, statusCode, statusMessage, statusType}`
- in the code: not used yet

### `GET /api/pricing/settlement-pricing/view/bulk/CALCULATE_SELLING_PRICE`

- seen 1x, status 200, from page `/Pricing/recommendations`
- answer: `{result: {fileLink, numberOfStyles}, statusCode, statusMessage, statusType}`
- in the code: not used yet

### `GET /api/seller-dashboard/actions-cards`

- seen 3x, status 200, from page `/Dashboard`
- query: `journey_stage`, `page`, `pageSize`, `page_code`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: [{sellerCardId, cardId, cardRuleId, cardName, description, priorityWeight, masterCategoryPriorityWeight, cardType, masterCategory, targetJourneyStage, redirectionUrl, displayProps, navigationHeading, isActive, cardImageUrl, cardIconName, payloadClicks, redirectionClicks, status, isPayload, createdAt, updatedAt}]}`
- in the code: not used yet

### `POST /api/seller-dashboard/actions-cards/card-event`

- seen 3x, status 200, from page `/Dashboard`
- body: `{eventName, sessionId, requestId, totalCardsOnPage, pageCode, journeyStage, sellerCardIds: […], cardIds: […], cardNames: […], masterCategories: […], priorityWeights: […], effectivePriorities: […]}`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: […]}`
- in the code: not used yet

### `GET /api/seller-dashboard/home/summary`

- seen 3x, status 200, from page `/Dashboard`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: {sales: {today: {period, gmv: {…}, change_label, orders_received: {…}}, this_week: {period, gmv: {…}, change_label, orders_received: {…}}}, orders: {period, fulfilled, cancellation_requests, return_requests, pending_packing, pending_handover}}}`
- in the code: not used yet

### `GET /api/seller-dashboard/summary`

- seen 3x, status 200, from page `/Dashboard`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: {seller: {last_refresh_time}, tabs: {overview: {label, metric: {…}}, listing_and_inventory: {label, metric: {…}, health, gmv_impact}, pricing: {label, metric: {…}, health, gmv_impact}, customer_impressions: {label, metric: {…}, health, gmv_impact}}}}`
- in the code: not used yet

### `POST /api/spf/createRnrBulkTickets`

- seen 2x, status 200, from page `/SPF`
- body: `{fileUrl, description, issueCategory, modelType}`
- answer: `{jobId}`
- in the code: not used yet

### `GET /api/spf/fetchNewClaim`

- seen 1x, status 200, from page `/SPF`
- query: `fetchAccio`, `id`
- answer: `{data: [{orderId, returnId, trackingId, returnTrackingId, skuId, orderLineId, returnCreatedDate, rejectionReason, styleId, orderCreatedOn, orderStatus, orderCancelDate, sellerId, warehouseId, orderPackedDate, orderShippedDate, orderDeliveredDate, isRefunded, orderCreatedBy, returnMode, returnReason, finalAmount, meta, styleInfo: {imageLink, imageLink360px, styleBasic: {…}}}], status: {statusCode, statusMessage, statusType, totalCount}}`
- in the code: not used yet

### `GET /api/spf/v2/fetchClaimByTicketId`

- seen 2x, status 200, from page `/SPF`
- query: `fetchAccio`, `id`
- answer: `{data: [{ticketId, modelType, status, issueCategory, description, createdOn, lastModifiedOn, history, validationReason, fwTicketId, styleId, skuId, compensationAmount, utr, paymentInitiatedOn, shippingLabelProofUrls: […], productProofUrls: […], videoProofUrls: […], orderId, orderLineId, returnId, trackingId, sellerOrderId, returnType, returnRequest, returnCreatedDate, returnDeliveredDate, physicalReceivedSku, sellerNotifiedAmount, returnTrackingId, eligibleForTagLoop, tagLoopId, finalAmount, ocrVerified, factCoreId, styleName, brandName, articleType, mrp, myntraSkuCode}], status: {statusCode, statusMessage, statusType, totalCount}}`
- in the code: `myntra.py`

### `GET /api/spf/v2/getTickets`

- seen 7x, status 200, from page `/SPF`
- query: `fetchAccio`, `modelType`, `page`, `pageSize`, `status`
- answer: `{data: [{ticketId, modelType, styleId, skuId, orderId, orderLineId, returnId, factCoreId, roNumber, issueCategory, createdOn, lastModifiedOn, status, styleInfo: {imageLink, imageLink360px, styleBasic: {…}}}], status: {statusCode, statusMessage, statusType, totalCount}}`
- in the code: `myntra.py`

### `POST /api/warehouse/getWarehouseDetailsInBulk`

- seen 2x, status 200, from page `/OTC`
- body: `{data: […]}`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data: [{id, name, barcode, address, city, state, stateId, postalCode, country, tinNumber, zones: […], isStandard, capacity, status, warehouseType}]}`
- in the code: not used yet
<!-- /AUTO:catalogue -->

## Notes (by hand)

- 
