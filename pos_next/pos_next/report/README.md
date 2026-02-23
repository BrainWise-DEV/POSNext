# POS Next Pro - Reports Documentation

This directory contains the reporting modules for POS Next Pro. All reports are implemented as Frappe Script Reports and are accessible from the Frappe Desk.

## Available Reports

### 1. Sales vs Shifts Report
**Path:** `sales_vs_shifts_report/`

Analyzes sales performance by shift, providing comprehensive shift-level metrics.

**Key Metrics:**
- Total sales per shift
- Invoice count
- Average ticket size
- Total discounts applied
- Return count and amount
- Net sales (sales minus returns)
- Efficiency score (calculated based on sales volume, returns, and discounts)

**Filters:**
- Date range (from/to)
- Specific shift
- POS Profile
- Cashier

**Use Cases:**
- Identify peak and slow shifts
- Measure shift productivity
- Compare cashier performance across shifts
- Track return rates by shift

---

### 2. Cashier Performance Report
**Path:** `cashier_performance_report/`

Evaluates individual cashier performance based on multiple metrics.

**Key Metrics:**
- Total sales by cashier
- Number of invoices processed
- Average invoice value
- Discounts given (amount and percentage)
- Returns processed (count and amount)
- Net sales
- Shifts worked
- Average sales per shift
- Performance rating (Excellent/Good/Average/Needs Improvement)

**Performance Rating Factors:**
- Sales volume (30%)
- Invoice count (20%)
- Low return rate (25%)
- Reasonable discount rate (25%)

**Filters:**
- Date range (from/to)
- Specific shift
- POS Profile
- Specific cashier

**Use Cases:**
- Performance reviews
- Identify top performers
- Training needs identification
- Bonus/incentive calculations

**Features:**
- Bar chart showing top 10 performers
- Color-coded performance ratings

---

### 3. Payments and Cash Control Report
**Path:** `payments_and_cash_control_report/`

Tracks payment reconciliation and cash control for accurate daily reconciliation.

**Key Metrics:**
- Payment breakdown by method (cash, card, wallet, etc.)
- Expected vs actual amounts
- Variance/difference
- Variance percentage
- Reconciliation status
- Transaction count per payment method

**Status Indicators:**
- ✓ Balanced: Perfect match
- ~ Minor Variance: Within acceptable range (±10)
- ↑ Over: More than expected
- ↓ Short: Less than expected

**Filters:**
- Date range (from/to)
- Specific shift
- POS Profile
- Cashier

**Use Cases:**
- Daily cash reconciliation
- Identify cash handling discrepancies
- Audit trail for payment methods
- Monitor payment method usage

**Features:**
- Pie chart showing payment method distribution
- Automatic variance calculation
- Transaction count tracking

---

### 4. Inventory Impact and Fast Movers Report
**Path:** `inventory_impact_and_fast_movers_report/`

Connects sales activity to inventory movement, highlighting stock depletion and fast-moving items.

**Key Metrics:**
- Quantity sold per item
- Total sales value
- Average selling rate
- Current stock level
- Stock depletion rate (per day)
- Days to stockout
- Stock status (color-coded)
- Velocity rank (A/B/C/D classification)
- Reorder level suggestion

**Stock Status Indicators:**
- 🔴 Out of Stock: No stock available
- 🟠 Critical: Less than 7 days stock
- 🟡 Low: 7-14 days stock
- 🟢 Good: 14-30 days stock
- 🔵 Excess: More than 30 days stock

**Velocity Rankings:**
- A - Fast Mover (Top 20%)
- B - Medium Mover (20-50%)
- C - Slow Mover (50-80%)
- D - Very Slow (Bottom 20%)

**Filters:**
- Date range (from/to)
- Specific shift
- POS Profile
- Item group

**Use Cases:**
- Inventory replenishment planning
- Identify best-selling items
- Prevent stockouts
- Optimize inventory levels
- Category performance analysis

**Features:**
- Bar chart showing top 15 fast movers
- Automatic reorder level calculation
- Color-coded stock status

---

### 5. Offline Sync and System Health Report
**Path:** `offline_sync_and_system_health_report/`

Monitors offline usage, synchronization status, and system health for reliable POS operations.

**Key Metrics:**
- Offline invoice sync status
- Sync delay in hours
- Health status indicators
- Error messages for failed syncs
- Success rate percentage
- Average sync delay

**Health Status Indicators:**
- ✅ Synced: Successfully synchronized
- 🟢 Synced (Slow): Synced with 1-24 hour delay
- 🟠 Delayed Sync: Synced after 24+ hours
- 🟡 Pending: Awaiting synchronization
- 🔴 Failed: Synchronization failed
- ❓ Unknown: Unknown status

**Summary Statistics:**
- Total sync attempts
- Successfully synced count
- Failed syncs count
- Pending syncs count
- Success rate percentage
- Average sync delay in hours

**Filters:**
- Date range (from/to)
- POS Profile
- Sync status (Pending/Synced/Failed)
- User

**Use Cases:**
- Monitor offline mode reliability
- Identify sync issues
- Troubleshoot failed synchronizations
- Track system performance
- Network health monitoring

**Features:**
- Donut chart showing sync status distribution
- Comprehensive summary section
- Error message tracking
- Sync delay analysis

---

## Technical Implementation

### File Structure

Each report follows this structure:
```
report_name/
├── __init__.py                  # Module initialization
├── report_name.json            # Report metadata (Frappe DocType)
├── report_name.py              # Python backend logic
└── report_name.js              # Frontend filters and formatting
```

### Backend (Python)

Each Python file implements:
- `execute(filters=None)`: Main entry point
- `get_columns()`: Define report columns
- `get_data(filters)`: Query and process data
- `get_conditions(filters)`: Build SQL WHERE clauses
- `get_chart_data(data)`: Optional chart configuration
- `get_summary(data)`: Optional summary statistics

### Frontend (JavaScript)

Each JS file configures:
- Filter definitions
- Default filter values
- Custom formatters for visual enhancements
- Column-specific styling

### Database Access

Reports use:
- **Frappe ORM**: For simple queries
- **SQL queries**: For complex joins and aggregations
- **Query Builder**: For type-safe query construction

### Performance Considerations

- Efficient SQL queries with proper indexing
- Date range filtering to limit dataset size
- Aggregation at database level
- Minimal post-processing in Python

---

## Access Control

All reports are accessible to users with the following roles:
- System Manager (all reports)
- Sales Manager (all reports)
- Accounts Manager (financial reports)
- Stock Manager (inventory report)
- POS User (shift and sales reports)

---

## Usage Instructions

### Accessing Reports

1. Navigate to **Frappe Desk**
2. Go to **Reports** in the sidebar
3. Select the desired report from the list
4. Apply filters as needed
5. Click **Refresh** to generate the report

### Exporting Reports

All reports support:
- **Export to Excel**: Click "Export" → "Excel"
- **Export to PDF**: Click "Export" → "PDF"
- **Print**: Click "Print" icon

### Scheduling Reports

Reports can be scheduled for automatic generation:
1. Click "Set Prepared Report" in the report
2. Configure schedule (daily, weekly, monthly)
3. Set email recipients
4. Report will be auto-generated and emailed

---

## Customization

### Adding New Filters

Edit the `.js` file and add to the `filters` array:

```javascript
{
    "fieldname": "custom_filter",
    "label": __("Custom Filter"),
    "fieldtype": "Link",
    "options": "DocType Name"
}
```

### Modifying Columns

Edit the `get_columns()` function in the `.py` file:

```python
{
    "fieldname": "new_column",
    "label": _("New Column"),
    "fieldtype": "Currency",
    "width": 130
}
```

### Adding Custom Metrics

Add calculations in the `get_data()` function:

```python
for row in data:
    row.custom_metric = calculate_custom_metric(row)
```

---

## Troubleshooting

### Reports Not Appearing

```bash
cd /home/ubuntu/frappe-bench
bench --site [site-name] clear-cache
bench build --app pos_next
```

### Performance Issues

- Reduce date range
- Add indexes to frequently queried fields
- Optimize SQL queries
- Use prepared reports for large datasets

### Incorrect Data

- Verify shift closing is complete
- Check invoice submission status
- Ensure proper date filters
- Validate POS Profile configuration

---

## Development

### Creating a New Report

1. Create directory: `pos_next/pos_next/report/new_report/`
2. Create files: `__init__.py`, `new_report.json`, `new_report.py`, `new_report.js`
3. Define columns and data query
4. Add filters and formatting
5. Clear cache and rebuild: `bench clear-cache && bench build`

### Testing

Test reports with:
- Empty datasets
- Large datasets (1000+ records)
- Various filter combinations
- Different user roles
- Export functionality

---

## Support

For issues or feature requests:
- GitHub: [https://github.com/BrainWise-DEV/POSNextPro](https://github.com/BrainWise-DEV/POSNextPro)
- Email: support@brainwise.me

---

## License

AGPL-3.0

Copyright (c) 2026, BrainWise
