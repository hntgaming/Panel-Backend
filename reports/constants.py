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

# Additional metrics that work with managed inventory
extended_metrics = [
    "TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS"  # Works with all dimensions, doesn't conflict
]

# Updated dimension metrics for Managed Inventory Publisher Dashboard
# Using core + extended metrics (TOTAL_AD_REQUESTS removed due to conflicts)
dimension_metrics = {
    "overview": core_metrics + extended_metrics,
    "site": core_metrics + extended_metrics,
    "trafficSource": core_metrics + extended_metrics,
    "deviceCategory": core_metrics + extended_metrics,
    "country": core_metrics + extended_metrics,
    "adunit": core_metrics + extended_metrics,  # Will use AD_UNIT_ID for hierarchical path
    "inventoryFormat": core_metrics + extended_metrics,
    "browser": core_metrics + extended_metrics,
}

# Default metrics for backward compatibility
metrics = core_metrics
