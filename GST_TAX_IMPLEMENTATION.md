# GST Tax Implementation in POS Next

## Overview

This implementation provides comprehensive GST tax handling in POS Next, similar to India Compliance's functionality. It properly determines place of supply, detects inter-state vs intra-state supplies, and selects the appropriate tax template (SGST+CGST or IGST).

## Key Features

1. **Place of Supply Determination**
   - Uses customer GSTIN state code (for registered customers)
   - Falls back to customer address state (for unregistered customers)
   - Handles overseas customers
   - Format: "27-Maharashtra" (state_code-state_name)

2. **Inter-State Detection**
   - Compares place of supply state with company state
   - Handles SEZ customers (always inter-state)
   - Returns boolean: `True` for inter-state (IGST), `False` for intra-state (SGST+CGST)

3. **Tax Template Selection**
   - First tries Tax Category integration (if India Compliance is installed)
   - Falls back to template name patterns
   - Supports both naming conventions

## Files Created/Modified

### New Files

1. **`pos_next/api/gst_tax.py`**
   - Comprehensive GST tax utilities module
   - Functions:
     - `get_place_of_supply()` - Determines place of supply
     - `is_inter_state_supply()` - Checks if inter-state
     - `get_gst_tax_template()` - Gets appropriate tax template
     - `get_gst_details()` - Main API endpoint for GST details

### Modified Files

1. **`pos_next/api/pos_profile.py`**
   - Updated `get_taxes()` function to use new GST utilities
   - Now accepts `shipping_address` parameter
   - Returns `place_of_supply` in response

2. **`pos_next/api/invoices.py`**
   - Updated invoice creation to use comprehensive GST utilities
   - Considers customer address, not just GSTIN

3. **`pos_next/api/__init__.py`**
   - Added `gst_tax` module import

## How It Works

### Flow Diagram

```
Customer Selection
    ↓
Get Customer Details (GSTIN, GST Category, Address)
    ↓
Determine Place of Supply
    ├─ Registered Customer → Use GSTIN state code
    ├─ Unregistered Customer → Use address state
    └─ Overseas Customer → Use shipping address or "96-Other Countries"
    ↓
Compare Place of Supply State with Company State
    ↓
Is Inter-State?
    ├─ Yes → Select IGST Template
    └─ No → Select SGST+CGST Template
    ↓
Apply Tax Template to Invoice
```

### Example Scenarios

#### Scenario 1: Same State (Intra-State)
- **Company**: Maharashtra (GSTIN: 27XXXXX...)
- **Customer**: Maharashtra (GSTIN: 27YYYYY...)
- **Result**: SGST + CGST (Intra-state template)

#### Scenario 2: Different State (Inter-State)
- **Company**: Maharashtra (GSTIN: 27XXXXX...)
- **Customer**: Karnataka (GSTIN: 29YYYYY...)
- **Result**: IGST (Inter-state template)

#### Scenario 3: Unregistered Customer
- **Company**: Maharashtra (GSTIN: 27XXXXX...)
- **Customer**: No GSTIN, Address in Karnataka
- **Result**: IGST (Inter-state template)

## API Usage

### Get Taxes for Customer

```python
# Via API
GET /api/method/pos_next.api.pos_profile.get_taxes
Parameters:
  - pos_profile: "POS Profile Name"
  - customer: "Customer Name" (optional)
  - shipping_address: "Address Name" (optional)

Response:
{
  "taxes": [...],
  "tax_template": "Output GST In-state - Company",
  "is_inter_state": false,
  "place_of_supply": "27-Maharashtra"
}
```

### Get GST Details

```python
# Via API
GET /api/method/pos_next.api.gst_tax.get_gst_details
Parameters:
  - customer: "Customer Name"
  - company: "Company Name"
  - shipping_address: "Address Name" (optional)

Response:
{
  "place_of_supply": "27-Maharashtra",
  "is_inter_state": false,
  "tax_template": "Output GST In-state - Company",
  "company_state_code": "27",
  "customer_state_code": "27"
}
```

## Integration with India Compliance

If India Compliance is installed, the implementation will:
1. Use Tax Category for template selection (more accurate)
2. Use STATE_NUMBERS constant for state name lookup
3. Follow India Compliance's GST rules

If India Compliance is not installed, it falls back to:
1. Template name pattern matching
2. Address state lookup
3. Basic GSTIN state code extraction

## Testing

To test the implementation:

1. **Same State Customer**:
   - Create customer with GSTIN from same state as company
   - Select customer in POS
   - Verify SGST+CGST template is applied

2. **Different State Customer**:
   - Create customer with GSTIN from different state
   - Select customer in POS
   - Verify IGST template is applied

3. **Unregistered Customer**:
   - Create customer without GSTIN
   - Set address in different state
   - Verify IGST template is applied

## Notes

- The implementation handles edge cases like missing addresses, invalid GSTINs, etc.
- Tax templates must follow naming conventions or use Tax Category
- Shipping address takes precedence over billing address for place of supply
- SEZ customers always use inter-state (IGST) templates

## Future Enhancements

- Support for Tax Category priority
- Integration with India Compliance's GST Settings
- Support for reverse charge mechanism (RCM)
- E-waybill integration based on place of supply
