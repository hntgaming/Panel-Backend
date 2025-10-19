# reports/constants.py

# Updated dimensions for Managed Inventory Publisher Dashboard
# Added adunit and inventory_format
dimension_map = {
    "overview": ["DATE"],  # Base dimension
    "site": ["SITE_NAME"],  # App/Site dimension
    "trafficSource": ["MOBILE_APP_NAME"],  # Traffic source dimension
    "deviceCategory": ["DEVICE_CATEGORY_NAME"],  # Device category dimension
    "country": ["COUNTRY_NAME"],  # Country dimension
    "adunit": ["AD_UNIT_NAME"],  # Ad Unit Name dimension
    "inventoryFormat": ["INVENTORY_FORMAT"],  # Inventory Format dimension
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

# Additional metrics that work with most dimensions
extended_metrics = [
    "TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS"
]

# Metrics that only work with overview and some specific dimensions
limited_metrics = [
    "TOTAL_AD_REQUESTS"
]

# Updated dimension metrics for Managed Inventory Publisher Dashboard
# TOTAL_AD_REQUESTS only works with overview dimension
dimension_metrics = {
    "overview": core_metrics + extended_metrics + limited_metrics,  # Overview supports all metrics
    "site": core_metrics + extended_metrics,  # TOTAL_AD_REQUESTS not compatible
    "trafficSource": core_metrics + extended_metrics,  # TOTAL_AD_REQUESTS not compatible
    "deviceCategory": core_metrics + extended_metrics,  # TOTAL_AD_REQUESTS not compatible
    "country": core_metrics + extended_metrics,  # TOTAL_AD_REQUESTS not compatible
    "adunit": core_metrics + extended_metrics,  # TOTAL_AD_REQUESTS not compatible
    "inventoryFormat": core_metrics + extended_metrics,  # TOTAL_AD_REQUESTS not compatible
    "browser": core_metrics + extended_metrics,  # TOTAL_AD_REQUESTS not compatible
}

# Default metrics for backward compatibility
metrics = core_metrics + extended_metrics
