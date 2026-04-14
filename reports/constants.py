# reports/constants.py

# Updated dimensions for Managed Inventory Publisher Dashboard
# Added adunit and inventory_format
dimension_map = {
    "overview": ["DATE"],  # Base dimension
    "site": ["SITE_NAME"],  # App/Site dimension
    "trafficSource": ["MOBILE_APP_NAME"],  # Traffic source dimension
    "deviceCategory": ["DEVICE_CATEGORY_NAME"],  # Device category dimension
    "country": ["COUNTRY_NAME"],  # Country dimension
    "adunit": ["AD_UNIT_ID", "AD_UNIT_NAME"],  # Ad Unit with hierarchical path (ID shows full path)
    "inventoryFormat": ["INVENTORY_FORMAT_NAME"],  # Inventory Format name (Banner, Interstitial, etc.)
    "browser": ["BROWSER_NAME"],  # Browser dimension
}

# Core metrics that work with all dimensions - using all available API data
core_metrics = [
    "AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS",
    "AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE", 
    "AD_EXCHANGE_LINE_ITEM_LEVEL_AVERAGE_ECPM",     # Use API-provided ECPM directly
    "AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS",
    "AD_EXCHANGE_LINE_ITEM_LEVEL_CTR",              # Use API-provided CTR directly
    "AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS_RATE",
    # Additional metrics available from API
    "AD_SERVER_IMPRESSIONS",
    "AD_SERVER_CLICKS", 
    "AD_SERVER_CTR",
    "AD_SERVER_CPM_AND_CPC_REVENUE",
    "AD_SERVER_WITHOUT_CPD_AVERAGE_ECPM"
]

# Ad-request metrics — TOTAL_AD_REQUESTS works reliably for overview/site/device
# but can conflict with some dimension combos (adunit, inventoryFormat).
# TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS is a safe alternative for all dimensions.
ad_request_metrics = [
    "TOTAL_AD_REQUESTS",
    "TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS",
]

ad_request_metrics_safe = [
    "TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS",
]

dimension_metrics = {
    "overview": core_metrics + ad_request_metrics,
    "site": core_metrics + ad_request_metrics,
    "deviceCategory": core_metrics + ad_request_metrics,
    "country": core_metrics + ad_request_metrics,
    "trafficSource": core_metrics + ad_request_metrics_safe,
    "adunit": core_metrics + ad_request_metrics_safe,
    "inventoryFormat": core_metrics + ad_request_metrics_safe,
    "browser": core_metrics + ad_request_metrics_safe,
}

# Default metrics for backward compatibility
metrics = core_metrics
