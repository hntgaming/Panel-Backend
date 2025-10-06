# Sub-Reports System Documentation

## Overview

The Sub-Reports system is an optimized reporting mechanism designed for timeframe-based aggregated data analysis in the GAM Sentinel platform. It provides efficient data fetching, processing, and storage for various dimensions with enhanced geo-spoofing detection capabilities.

## Key Features

### 🎯 **Timeframe-Based Aggregation**
- **Month to Date (MTD)**: Current month's data from 1st to today
- **Last Month**: Complete previous month's data
- **Last 3 Months**: Rolling 3-month period
- **Last 6 Months**: Rolling 6-month period

### 📊 **Multi-Dimensional Analysis**
- **Site**: Website-level aggregation
- **Traffic Source**: Mobile app traffic analysis
- **Device Category**: Desktop, Mobile, Tablet, Connected TV
- **Country**: Geographic distribution analysis
- **Carrier**: Mobile carrier analysis
- **Browser**: Browser usage patterns
- **Country-Carrier**: Combined geo-spoofing detection

### 🔍 **Advanced Geo-Spoofing Detection**
- **Combined Dimension Analysis**: Uses both country and carrier data together
- **Legitimate Carrier Mapping**: Comprehensive database of carrier-country combinations
- **Real-time Detection**: Identifies suspicious traffic patterns
- **Comprehensive Coverage**: 500+ carrier-country combinations mapped

## Architecture

### Core Components

#### 1. **Models** (`sub_reports/models.py`)
```python
class SubReportData(models.Model):
    # Source relationships
    parent_network = models.ForeignKey(GAMNetwork)
    invitation = models.ForeignKey(MCMInvitation)
    
    # Network identification
    child_network_code = models.CharField(max_length=20)
    partner_id = models.IntegerField()
    
    # Timeframe and dimension data
    timeframe = models.CharField(max_length=20, choices=TIMEFRAME_CHOICES)
    dimension_type = models.CharField(max_length=20, choices=DIMENSION_CHOICES)
    dimension_value = models.CharField(max_length=500)
    
    # Core metrics with decimal precision
    revenue = models.DecimalField(max_digits=10, decimal_places=2)
    ecpm = models.DecimalField(max_digits=8, decimal_places=4)
    impressions = models.BigIntegerField()
    clicks = models.BigIntegerField()
    ctr = models.DecimalField(max_digits=5, decimal_places=2)
    
    # Unknown traffic analysis
    unknown_revenue = models.DecimalField(max_digits=10, decimal_places=2)
    unknown_ecpm = models.DecimalField(max_digits=8, decimal_places=2)
    unknown_impressions = models.BigIntegerField()
    unknown_ctr = models.DecimalField(max_digits=5, decimal_places=2)
    
    # Additional metrics
    total_ad_requests = models.BigIntegerField()
    fill_rate = models.DecimalField(max_digits=5, decimal_places=2)
    viewable_impressions_rate = models.DecimalField(max_digits=5, decimal_places=2)
```

#### 2. **Services** (`sub_reports/services.py`)
```python
class SubReportService:
    # Dimension mapping for GAM API calls
    DIMENSION_MAP = {
        "site": ["SITE_NAME"],
        "trafficSource": ["MOBILE_APP_NAME"],
        "deviceCategory": ["DEVICE_CATEGORY_NAME"],
        "country": ["COUNTRY_NAME"],
        "carrier": ["CARRIER_NAME"],
        "browser": ["BROWSER_NAME"],
        "country_carrier": ["COUNTRY_NAME", "CARRIER_NAME"]  # Combined dimension
    }
    
    # Core metrics for all dimensions
    METRICS = [
        "AD_EXCHANGE_LINE_ITEM_LEVEL_IMPRESSIONS",
        "AD_EXCHANGE_LINE_ITEM_LEVEL_REVENUE",
        "AD_EXCHANGE_LINE_ITEM_LEVEL_AVERAGE_ECPM",
        "AD_EXCHANGE_LINE_ITEM_LEVEL_CLICKS",
        "AD_EXCHANGE_LINE_ITEM_LEVEL_CTR",
        "AD_EXCHANGE_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS_RATE"
    ]
```

#### 3. **Views** (`sub_reports/views.py`)
```python
class PreVetChildView(APIView):
    """
    Pre-vetting analysis for child networks with comprehensive geo-spoofing detection
    """
    
    def post(self, request):
        # Calculate vetting scores for all timeframes
        # Include geo-spoofing detection using country-carrier combinations
        # Return comprehensive risk analysis
```

## Geo-Spoofing Detection System

### How It Works

1. **Data Collection**: Fetches combined `COUNTRY_NAME` and `CARRIER_NAME` dimensions from GAM
2. **Combination Analysis**: Creates country-carrier pairs (e.g., "United States | T-Mobile (US)")
3. **Legitimacy Check**: Compares against comprehensive carrier-country database
4. **Risk Assessment**: Flags suspicious combinations for further investigation

### Example Detection

```python
# Legitimate combination
"United States | T-Mobile (US)" ✅ LEGITIMATE

# Geo-spoofing detected
"Puerto Rico | T-Mobile (US)" 🚨 GEO-SPOOFING
# T-Mobile (US) should only operate in United States
```

### Carrier Database Coverage

The system includes **500+ carrier-country combinations** covering:
- **Major Carriers**: Verizon, AT&T, T-Mobile, Vodafone, Orange, MTN
- **Regional Carriers**: Airtel, Reliance Jio, Telcel, Claro, Movistar
- **Global Coverage**: 150+ countries with legitimate carrier mappings
- **Special Cases**: Roaming agreements and international operations

## API Endpoints

### 1. **Pre-Vetting Analysis**
```http
POST /api/sub-reports/pre-vet/
Content-Type: application/json

{
    "child_network_code": "22878573653"
}
```

**Response:**
```json
{
    "child_network_code": "22878573653",
    "timeframes": {
        "month_to_date": {
            "score": 85,
            "label": "Good",
            "signals": {
                "unknown_cpm": 2.94,
                "unfilled_rate": 15.2,
                "carrier_country_mismatch": 1,
                "country_concentration": 208,
                "carrier_concentration": 218
            },
            "date_from": "2025-09-01",
            "date_to": "2025-09-22"
        }
    }
}
```

### 2. **Query Sub-Reports**
```http
POST /api/sub-reports/query/
Content-Type: application/json

{
    "child_network_code": "22878573653",
    "timeframe": "month_to_date",
    "dimension_type": "country_carrier"
}
```

### 3. **List Networks**
```http
GET /api/sub-reports/networks/
```

### 4. **Get Statistics**
```http
GET /api/sub-reports/stats/
```

### 5. **Trigger Sync**
```http
POST /api/sub-reports/sync/
Content-Type: application/json

{
    "child_network_code": "22878573653",
    "timeframe": "month_to_date"
}
```

## Management Commands

### Test Sub-Report Sync
```bash
python manage.py test_sub_report_sync \
    --child-network 22878573653 \
    --timeframe month_to_date \
    --force-sync
```

**Options:**
- `--child-network`: Network code to sync
- `--timeframe`: One of `month_to_date`, `last_month`, `last_3_months`, `last_6_months`
- `--force-sync`: Override existing data

## Data Processing Pipeline

### 1. **GAM API Integration**
- Connects to Google Ad Manager API
- Fetches report data for specified dimensions
- Handles authentication and rate limiting
- Processes CSV response data

### 2. **Data Transformation**
- Converts micros currency to decimal values
- Calculates derived metrics (eCPM, CTR, Fill Rate)
- Handles unknown traffic analysis
- Applies decimal precision constraints

### 3. **Storage Optimization**
- Batch processing for large datasets
- Efficient database indexing
- Duplicate prevention
- Error handling and retry logic

### 4. **Geo-Spoofing Analysis**
- Parses country-carrier combinations
- Validates against legitimate mappings
- Calculates mismatch scores
- Generates risk assessments

## Performance Optimizations

### Database Indexing
```python
# Optimized indexes for fast queries
db_index=True  # On frequently queried fields
```

### Batch Processing
```python
BATCH_SIZE = 500  # Optimal batch size for aggregated data
```

### Caching Strategy
```python
CACHE_TIMEOUT = 300  # 5 minutes cache for aggregated data
```

### Memory Management
- Efficient data structures
- Lazy loading for large datasets
- Garbage collection optimization

## Error Handling

### Common Issues and Solutions

#### 1. **Decimal Precision Errors**
```python
# Ensure proper decimal precision
revenue = Decimal(str(value)).quantize(Decimal('0.00'))
ecpm = Decimal(str(value)).quantize(Decimal('0.0000'))
```

#### 2. **Dimension Mutation**
```python
# Create copies to avoid mutating shared objects
dims = list(base_dims)  # Instead of direct reference
```

#### 3. **GAM API Limits**
- Automatic retry with exponential backoff
- Rate limiting compliance
- Error logging and monitoring

## Monitoring and Logging

### Log Levels
- **INFO**: Successful operations and data processing
- **WARNING**: Non-critical issues and fallbacks
- **ERROR**: Failed operations requiring attention
- **DEBUG**: Detailed processing information

### Key Metrics
- **Sync Success Rate**: Percentage of successful data fetches
- **Processing Time**: Time taken for data transformation
- **Error Rate**: Frequency of processing failures
- **Data Quality**: Validation of processed data

## Security Considerations

### Authentication
- JWT token-based authentication
- Role-based access control
- API rate limiting

### Data Privacy
- Secure data transmission (HTTPS)
- Encrypted data storage
- Access logging and auditing

### Input Validation
- Sanitized input parameters
- SQL injection prevention
- XSS protection

## Troubleshooting Guide

### Common Problems

#### 1. **Sync Failures**
```bash
# Check GAM API credentials
# Verify network permissions
# Review error logs
```

#### 2. **Data Inconsistencies**
```bash
# Clear existing data
# Force re-sync
# Validate data integrity
```

#### 3. **Performance Issues**
```bash
# Check database indexes
# Monitor memory usage
# Optimize batch sizes
```

### Debug Commands
```bash
# Check data status
python manage.py shell -c "
from sub_reports.models import SubReportData
print(SubReportData.objects.count())
"

# Test specific timeframe
python manage.py test_sub_report_sync --child-network 22878573653 --timeframe month_to_date
```

## Future Enhancements

### Planned Features
1. **Real-time Monitoring**: Live data updates and alerts
2. **Advanced Analytics**: Machine learning-based risk assessment
3. **Custom Dimensions**: User-defined dimension combinations
4. **Export Capabilities**: Data export in multiple formats
5. **API Versioning**: Backward compatibility management

### Performance Improvements
1. **Parallel Processing**: Multi-threaded data fetching
2. **Incremental Updates**: Delta sync for changed data
3. **Compression**: Data compression for storage efficiency
4. **Caching**: Redis-based caching layer

## Contributing

### Development Setup
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up environment variables
4. Run migrations: `python manage.py migrate`
5. Start development server: `python manage.py runserver`

### Code Standards
- Follow PEP 8 style guidelines
- Write comprehensive tests
- Document all public APIs
- Use type hints where appropriate

### Testing
```bash
# Run all tests
python manage.py test

# Run specific test suite
python manage.py test sub_reports.tests
```

## Support

For technical support or questions:
- **Documentation**: This README and inline code comments
- **Logs**: Check application logs for detailed error information
- **API**: Use the management commands for debugging
- **Community**: GitHub issues and discussions

---

**Last Updated**: September 22, 2025  
**Version**: 1.0.0  
**Maintainer**: GAM Sentinel Development Team
