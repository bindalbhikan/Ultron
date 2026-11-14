# API calls seen on `partnersapi.myntrainfo.com`

What each call is for, and what is safe to do with it, is in
the portal's page in `docs/knowledge/`. Calls that change something (POST / PUT that
save, approve, raise or push) are never made by the agent without the owner's approval.

<!-- AUTO:catalogue -->
Generated 14 Nov 2026 by `scripts/knowledge/learn_netcap.py` from netcap-2026-11-01T19-31-31-606Z.json. Names only, no values.

### `GET /api/boot/partners`

- seen 14x, status 200, from page `/`, `/Dashboard`, `/Reports/seller-reports`
- query: `reloaded`
- answer: `{__version, device: {isMobile, isDesktop}, baseUrl, config: {cookie: {prefix, domain}, qcEngine: {security: {application: {…}, resource: {…}, teamTypes: [{…}]}}, services: {spf: {root, path}, voicePlatform: {root, path}, kuber: {root, path}, mlp: {root, path}, accio: {root, path}, gauntlet: {root, path}, settlementService: {root, path}, pricingEngine: {root, path, auth}, adwiser: {root, path}, mintAdvantage: {root, path}, mintAdventureGrpc: {root}, agreements: {root, path}, stockv2: {root, path, auth}, erpims: {root, path, auth}, irisAgent: {root, path, auth}, ugc: {root, path}, ratings: {root, path}, cmscatalogservice: {root, path, auth}, audit: {path, auth, root}, worms: {root, path, auth}, orderIntegration: {root, path}, mwsAirflow: {root, path}, ims: {path, auth, root}, atp: {path, aut`
- in the code: `myntra.py`

### `GET /api/diy-cataloguing/getAllArticleTypes`

- seen 11x, status 200, from page `/Catalog`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data: [{value, label, typeCode}]}`
- in the code: not used yet

### `GET /api/diy-cataloguing/getCountOfApprovalPending`

- seen 1x, status 200, from page `/Catalog`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}}`
- in the code: not used yet

### `GET /api/diy-cataloguing/getPartnerProductsWithPqi`

- seen 1x, status 200, from page `/Catalog`
- query: `fetchSize`, `q[q]`, `q[status]`, `sortBy`, `sortOrder`, `start`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data: [{productId, title, price, styleType, styleCategory, codEnabled, sizeChartDisplayType, sizeRepresentationUrlMap: {garment}, productOptions: [{…}], articleNumber, productDisplayName, listViewName, variantName, manufacturerInfo, countryOfOrigin, vendorHSN, hsnCode, sourceId, sourceInfo, addDate, modifiedDate, articleType: {filterOrder, typeName, typeCode, isActive, isSocialSharingEnabled, isJewellery, isReturnable, isExchangeable, isLarge, isHazmat, isTryAndBuyEnabled, pickupEnabled, attributeTagsPriorityList: [{…}], id, fragile}, subCatagory: {filterOrder, typeName, typeCode, isActive, parent1Id, parent2Id, parent3Id, trialAttributes: […], id, allAttributeTypeEntires: […]}, masterCatagory: {filterOrder, typeName, typeCode, `
- in the code: not used yet

### `GET /api/diy-cataloguing/getPqiSellerPerformance`

- seen 1x, status 200, from page `/Catalog`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data: […]}`
- in the code: not used yet

### `GET /api/diy-cataloguing/getProductsCount`

- seen 1x, status 200, from page `/Catalog`
- in the code: not used yet

### `POST /api/diy-cataloguing/style-grouping/bulk-upload/submit`

- seen 1x, status 200, from page `/Catalog`
- body: `{urlEntry: {fileName, url}, listingEntry: {listingComments, listingStatus}}`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, id, fileDownloadPath}`
- in the code: `myntra.py`

### `POST /api/diy-cataloguing/style-grouping/export/report`

- seen 1x, status 200, from page `/Catalog/my-requests`
- body: `{id: […]}`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, fileDownloadPath}`
- in the code: `myntra.py`

### `POST /api/diy-cataloguing/style-grouping/find/entries`

- seen 2x, status 200, from page `/Catalog/my-requests`
- body: `{pageNo, pageSize, sortOrder, sortBy}`
- answer: `{status: {statusCode, statusType, statusMessage, totalCount, currentCount}, pagination: {totalCount, pageSize, startIndex}, data: [{id, jobType, status, approvalStatus, sellerId, totalRecords, processedRecords, erredRecords, noOfChunks, retryCount, metaData: {source, jobType, sellerId, sellerName, uploadedBy, inputFilePath, partnerEmailId, signedInputFilePath}, messageData: {}, createdBy, inputFile, queueName, createdAt, updatedAt, startedOn, endedOn, bulkSubJobTracker, bulkJobRegistry: {id, jobType, chunkSize, maxRetries, maxEntries, jobQueueName, subJobQueueName, useSubJobQueue, concurrencyLimit, waitingLimit, config: {…}, metadata: {…}, createdBy, modifiedBy, createdAt, updatedAt, deletedAt, version}}]}`
- in the code: `myntra.py`

### `POST /api/diy-cataloguing/style-grouping/status/count`

- seen 2x, status 200, from page `/Catalog/my-requests`
- body: `{}`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, statusCounts: {PARTIAL_COMPLETE, COMPLETED, FAILED, WAITING}, totalCount}`
- in the code: not used yet

### `POST /api/diy-cataloguing/styletracker/find`

- seen 8x, status 200, from page `/Catalog`, `/Catalog/my-requests`
- body: `{pageNo, pageSize, styleId: […], createdOnFrom, createdOnTo}`
- answer: `{status: {statusCode, statusType, statusMessage, totalCount, currentCount}, pagination: {totalCount, pageSize, startIndex}, data: […]}`
- in the code: not used yet

### `GET /api/diy-cataloguing/v2/partnerBrands`

- seen 11x, status 200, from page `/Catalog`
- query: `buyerId`, `storeId`
- answer: `[{label, value}]`
- in the code: not used yet

### `GET /api/file-manager/getUploadToken/cms`

- seen 1x, status 200, from page `/Catalog`
- query: `fileNames`
- answer: `{005_Murcia_Co_Ords.xlsx: {sasUrl, fileNameWithPath}}`
- in the code: `myntra.py`

### `GET /api/file-manager/getUploadToken/spfJob`

- seen 2x, status 200, from page `/SPF`
- query: `fileNames`
- answer: `{{id}: {sasUrl, fileNameWithPath}}`
- in the code: `myntra.py`

### `GET /api/listings/betaSellers`

- seen 15x, status 200, from page `/Catalog`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data: [{label, value}]}`
- in the code: not used yet

### `GET /api/listings/checkppmp`

- seen 1x, status 200, from page `/Catalog`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data}`
- in the code: not used yet

### `GET /api/partners/leftnav/fbm-status`

- seen 2x, status 200, from page `/Dashboard`, `/Reports/seller-reports`
- answer: `{isFbm}`
- in the code: not used yet

### `GET /api/partners/notifications/announcements`

- seen 1x, status 200, from page `/Dashboard`
- query: `fetchSize`, `start`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data: [{id, recipients: […], clientType, status, state, priority, activationDate, expiryDate, misc: {content, groupNames, numberOfDays, title}, customData: {priority}, refId, createdOn, lastModifiedOn, createdBy, lastModifiedBy, isPWAEnabled}]}`
- in the code: not used yet

### `GET /api/partners/notifications/tasks`

- seen 6x, status 200, from page `/Dashboard`, `/Reports/seller-reports`
- query: `fetchSize`, `recipient`, `type`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, data}`
- in the code: not used yet

### `GET /api/partners/report/summary/next-payment`

- seen 2x, status 200, from page `/Dashboard`
- answer: `{status: {statusCode, statusMessage, statusType}, data: {paymentDate, prepaidAmount, postpaidAmount, totalAmount}}`
- in the code: not used yet

### `GET /api/partners/report/summary/outstanding-payment`

- seen 1x, status 200, from page `/Dashboard`
- answer: `{status: {statusCode, statusMessage, statusType}, data: {prepaidAmount, postpaidAmount, totalAmount, updated_at, detailsLink}}`
- in the code: not used yet

### `GET /api/partners/report/summary/payment-history`

- seen 1x, status 200, from page `/Dashboard`
- query: `fromDate`, `pageNo`, `pageSize`, `toDate`, `type`
- answer: `{status: {statusCode, statusMessage, statusType}, data: {totalElements, totalPages, totalAmount, prepaidAmount, postpaidAmount, payments: [{paymentMethod, utrNumber, paymentDate, yearMonth, amount, utrDetailsLink, adviceId}]}}`
- in the code: `myntra.py`

### `GET /api/partners/seller-activation/seller-achievements`

- seen 3x, status 200, from page `/Dashboard`, `/Reports/seller-reports`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: […]}`
- in the code: not used yet

### `GET /api/partners/seller-performance/contract-tier`

- seen 1x, status 200, from page `/Dashboard`
- answer: `{status: {statusType, statusMessage, statusCode}, data: [{term: {id, entityType, type, contractId, entityId, startedOn, endedOn, status, referenceId, tag, comments, remarks, createdBy, transitions, createdAt, updatedAt, autoRenewalEnabled, tier, autoRenewalCycle, model}, exception}]}`
- in the code: not used yet

### `GET /api/partners/seller-performance/dashboard`

- seen 1x, status 200, from page `/Dashboard`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: [{evalQuarter, dataInsertTime, metricScores: [{…}], totalStars, finalSellerTier, previousEvalQuarter, previousRevenue, previousUnits, previousPaymentAmount, previousTotalStars, previousO2pMetric, previousCancelMetric, previousBreachMetric, previousRuMetric, previousRatingMetric, previousFreshnessMetric, previousScrMetric, freshnessThresholdGold, thresholdScrGold, thresholdScrSilver, previousDataInsertTime}]}`
- in the code: not used yet

### `GET /api/partners/seller-performance/tier-cutoff`

- seen 1x, status 200, from page `/Dashboard`
- answer: `[{term: {id, entityType, type, contractId, entityId, startedOn, endedOn, status, referenceId, tag, comments, remarks, createdBy, transitions, createdAt, updatedAt, tierCutOff: [{…}]}, exception}]`
- in the code: not used yet

### `GET /api/partners/sellerreports/all-new`

- seen 1x, status 200, from page `/Reports/seller-reports`
- query: `month`, `year`
- answer: `{status: {statusType, statusCode, statusMessage}, data: {OTHERS: [{displayName, reportPath, reportName, appName, subType}]}}`
- in the code: not used yet

### `GET /api/partners/vms/v3/partner`

- seen 1x, status 200, from page `/Dashboard`
- query: `ids`
- answer: `{status: {statusCode, statusMessage, statusType, totalCount}, partnerEntries: [{id, createdBy, createdOn, lastModifiedOn, version, name, barcode, displayName, enabled, description, status, entityType, partnerType, msme, uuid, lastModifiedBy, remarks, partnerContactPersons: [{…}]}]}`
- in the code: not used yet

### `GET /api/seller-dashboard/actions-cards`

- seen 1x, status 200, from page `/Dashboard`
- query: `journey_stage`, `page`, `pageSize`, `page_code`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: [{sellerCardId, cardId, cardRuleId, cardName, description, priorityWeight, masterCategoryPriorityWeight, cardType, masterCategory, targetJourneyStage, redirectionUrl, displayProps, navigationHeading, isActive, cardImageUrl, cardIconName, payloadClicks, redirectionClicks, status, isPayload, createdAt, updatedAt}]}`
- in the code: not used yet

### `POST /api/seller-dashboard/actions-cards/card-event`

- seen 1x, status 200, from page `/Dashboard`
- body: `{eventName, sessionId, requestId, totalCardsOnPage, pageCode, journeyStage, sellerCardIds: […], cardIds: […], cardNames: […], masterCategories: […], priorityWeights: […], effectivePriorities: […]}`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: […]}`
- in the code: not used yet

### `GET /api/seller-dashboard/home/summary`

- seen 1x, status 200, from page `/Dashboard`
- answer: `{status: {totalCount, statusType, statusCode, statusMessage}, data: {sales: {today: {period, gmv: {…}, change_label, orders_received: {…}}, this_week: {period, gmv: {…}, change_label, orders_received: {…}}}, orders: {period, fulfilled, cancellation_requests, return_requests, pending_packing, pending_handover}}}`
- in the code: not used yet

### `GET /api/seller-dashboard/summary`

- seen 1x, status 200, from page `/Dashboard`
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
<!-- /AUTO:catalogue -->

## Notes (by hand)

- 
