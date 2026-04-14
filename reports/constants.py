# reports/constants.py

dimension_map = {
    "overview": ["DATE"],
    "site": ["SITE_NAME"],
    "trafficSource": ["MOBILE_APP_NAME"],
    "deviceCategory": ["DEVICE_CATEGORY_NAME"],
    "country": ["COUNTRY_NAME"],
    "adunit": ["AD_UNIT_ID", "AD_UNIT_NAME"],
    "inventoryFormat": ["INVENTORY_FORMAT_NAME"],
    "browser": ["BROWSER_NAME"],
}

core_metrics = [
    "AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS",
    "AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE",
    "AD_EXCHANGE_LINE_ITEM_LEVEL_AVERAGE_ECPM",
    "AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS",
    "AD_EXCHANGE_LINE_ITEM_LEVEL_CTR",
    "AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS_RATE",
    "AD_SERVER_IMPRESSIONS",
    "AD_SERVER_CLICKS",
    "AD_SERVER_CTR",
    "AD_SERVER_CPM_AND_CPC_REVENUE",
    "AD_SERVER_WITHOUT_CPD_AVERAGE_ECPM",
]

# TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS is universally compatible with
# every dimension + CHILD_NETWORK_CODE / SITE_NAME combo in GAM.
# TOTAL_AD_REQUESTS conflicts with CHILD_NETWORK_CODE, SITE_NAME, AD_UNIT,
# INVENTORY_FORMAT, BROWSER — causing COLUMNS_NOT_SUPPORTED errors and
# wasted fallback API calls.  Use the single reliable metric everywhere.
ad_request_metrics = [
    "TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS",
]

dimension_metrics = {
    "overview":         core_metrics + ad_request_metrics,
    "site":             core_metrics + ad_request_metrics,
    "deviceCategory":   core_metrics + ad_request_metrics,
    "country":          core_metrics + ad_request_metrics,
    "trafficSource":    core_metrics + ad_request_metrics,
    "adunit":           core_metrics + ad_request_metrics,
    "inventoryFormat":  core_metrics + ad_request_metrics,
    "browser":          core_metrics + ad_request_metrics,
}

metrics = core_metrics
