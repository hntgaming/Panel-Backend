# reports/constants.py

# REPLICATED: Use exact same dimension mappings as working sub-reports
# DEVICE_CATEGORY_NAME is added dynamically in Stage 1 unknown processing
dimension_map = {
    "overview": ["DATE"],  # Base dimension - DEVICE_CATEGORY_NAME added dynamically for unknown processing
    "site": ["SITE_NAME"],  # Base dimension - DEVICE_CATEGORY_NAME added dynamically for unknown processing
    "trafficSource": ["MOBILE_APP_NAME"],  # Base dimension - DEVICE_CATEGORY_NAME added dynamically for unknown processing
    "deviceCategory": ["DEVICE_CATEGORY_NAME"],  # Same as sub-reports
    "country": ["COUNTRY_NAME"],  # Base dimension - DEVICE_CATEGORY_NAME added dynamically for unknown processing
    "carrier": ["CARRIER_NAME"],  # Base dimension - DEVICE_CATEGORY_NAME added dynamically for unknown processing
    "browser": ["BROWSER_NAME"],  # Base dimension - DEVICE_CATEGORY_NAME added dynamically for unknown processing
    # Combined dimensions for geo-spoofing detection
    "country_carrier": ["COUNTRY_NAME", "CARRIER_NAME"]  # Base dimensions - DEVICE_CATEGORY_NAME added dynamically for unknown processing
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

# REPLICATED: Use exact same dimension metrics as working sub-reports
dimension_metrics = {
    "overview": core_metrics + extended_metrics,  # Use only compatible metrics with DATE dimension
    "site": core_metrics + extended_metrics,  # TOTAL_AD_REQUESTS not compatible
    "trafficSource": core_metrics + extended_metrics,  # TOTAL_AD_REQUESTS not compatible
    "deviceCategory": core_metrics + extended_metrics + limited_metrics,
    "country": core_metrics + extended_metrics + limited_metrics,
    "carrier": core_metrics + extended_metrics,  # TOTAL_AD_REQUESTS not compatible
    "browser": core_metrics + extended_metrics + limited_metrics,
    "country_carrier": core_metrics + extended_metrics  # For geo-spoofing detection
}

# Default metrics for backward compatibility
metrics = core_metrics + extended_metrics
