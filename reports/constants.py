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
    "TOTAL_PROGRAMMATIC_ELIGIBLE_AD_REQUESTS",
]

dimension_metrics = {dim: list(core_metrics) for dim in dimension_map}

metrics = core_metrics
