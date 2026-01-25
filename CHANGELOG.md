# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.13.0] - 2026-01-07

### Added
- **POSNext Cashier Role & Permissions**
  - Created dedicated POSNext Cashier role for POS operations
  - Added custom permissions for Customer, Bin, Item, and Warehouse doctypes
  - Proper role-based access control for POS users

- **Offline Invoice Sync Enhancement**
  - Added deduplication mechanism for offline invoice synchronization
  - Prevents duplicate invoice creation during sync recovery
  - Defensive type checks and mutex for concurrent sync operations

- **Return Invoice Improvements**
  - Added item search functionality in Return Invoice Dialog
  - Improved code quality and user experience for returns

- **Shift Closing Enhancement**
  - Return invoices now included in shift closing calculations
  - More accurate end-of-day reporting

### Changed
- **Offers & Promotions Optimization**
  - Optimized apply_offers with batch queries for better performance
  - Added dynamic debounce for offer application
  - Support for standalone pricing rules in apply_offers
  - Validate min_qty against eligible item quantity instead of total cart
  - Ensures offers fetched before processing in mobile view
  - Added offline support for promotions with mixed conditions

- **Cart & Payment Improvements**
  - Corrected subtotal display for tax-inclusive mode
  - Enhanced mobile responsiveness and dynamic sizing in PaymentDialog
  - Restored Hold Order button functionality

- **Internationalization**
  - Fixed translation API and added missing translations
  - Improved i18n coverage across the application

- **Build & Dependencies**
  - Updated frappe-ui imports to use proper exports
  - Improved build compatibility

### Fixed
- **Offers System**
  - Fixed min_qty validation to check eligible item quantity, not total cart
  - Fixed standalone pricing rules not being applied correctly
  - Fixed offers not being fetched before processing in mobile view

- **Cart Display**
  - Fixed subtotal display in tax-inclusive mode showing incorrect values

- **Offline Sync**
  - Added defensive type checks preventing sync errors
  - Added mutex to prevent concurrent sync race conditions

- **UI/UX**
  - Fixed Hold Order button missing from cart (regression fix)
  - Enhanced mobile responsiveness in PaymentDialog

## [1.12.0] - 2025-12-18

### Added
- **Wallet & Loyalty Program System**
  - Implement wallet functionality with loyalty points conversion
  - Auto-assignment of loyalty programs for new customers
  - Auto-assignment of loyalty program on sales invoice validation
  - Partial payment support for wallet/loyalty points redemption
  - Enable Loyalty Program as master switch in Wallet & Loyalty settings
  - Comprehensive technical documentation for Wallet System

- **Customer Search Enhancements**
  - Enhanced customer search with autocomplete functionality
  - Frequent customers display for quick selection
  - Optimized click handler for instant response on frequent customers

- **Sales Order Support in POS**
  - Sales order settings and store methods exposure
  - Delivery date selection integrated into payment flow
  - Delivery date dialogue for order scheduling
  - Dropdown menu for selecting between sales order and sales invoice

- **POS Profile Management**
  - Create, update, and delete POS profiles via API
  - Whitelist decorators for POS profile functions
  - Enforce user company association on profile creation
  - Enhanced parameter parsing for profile operations

- **Customer Management**
  - Edit customer functionality directly from cart

- **Payment Dialog Improvements**
  - Two-column layout redesign with invoice summary
  - Long-press payment with new composable
  - Dynamic sizing and responsive design adjustments
  - Enhanced credit balance and additional discount display
  - Improved mobile UX

- **Localization**
  - Configurable language settings
  - Brazilian Portuguese (pt-BR) support
  - RTL-friendly SelectInput component

- **Warehouse & Stock**
  - Loading state and improved stock availability logic in WarehouseAvailabilityDialog
  - Optimized bundle availability calculation across warehouses
  - Improved stock visibility and translation in warehouse dialogs

- **Draft Invoice Features**
  - Print button for draft invoices
  - Auto-save active cart when switching drafts

- **Coupon Management**
  - Validate coupon endpoint for gift cards
  - Enhanced customer selection in coupon management

- **Settings Organization**
  - Split POS Settings into organized tabs

### Changed
- **Cart Operations**
  - Refactored updateQuantity function to improve item removal logic
  - Improved UOM selection UI and cart item handling

- **POS Profile Handling**
  - User company check utility moved to pos_next utilities
  - Refactored payment, user, item group, and customer group handling in profile update
  - Simplified profile creation with enhanced parameter parsing
  - Cleaned up imports in POS profile API

### Fixed
- **Offers & Promotions**
  - Race condition causing offers applied but cart not updating
  - Made offer processing more dynamic and robust
  - Enhanced offer management with automatic application and improved notifications

- **Stock Validation**
  - Fixed stock validation and double-add issue in ItemsSelector
  - Skip stock validation for non-stock items

- **RTL & Translation**
  - RTL alignment and translation in ShiftOpeningDialog
  - RTL overlap in OffersDialog badge positioning

- **Drafts**
  - Prevent draft deletion on load
  - Populate drafts store to show drafts in Invoice Management

- **Sales Order Compatibility**
  - Fixed 'SalesOrder' object attribute errors (outstanding_amount, is_return, payments)
  - Fixed "Value missing for Sales Order: Customer" error
  - Fixed ReferenceError issues (usePOSCartStore, cartStore not defined)
  - Fixed TypeError for NoneType multiplication with float
  - Fixed sales order submission on checkout

- **Payment Dialog RTL**
  - Improved RTL support and mobile responsiveness in PaymentDialog

## [1.11.0] - 2025-12-07

### Added
- **Multi-UOM Cart Support**
  - Support for adding same item with different Units of Measure (UOMs) to cart
  - Each UOM line is tracked independently with its own quantity and rate
  - Quantity input field in UOM selection dialog for faster item entry

- **Enhanced Stock Display**
  - Real-time available stock now subtracts cart quantities from displayed stock
  - Stock display accounts for conversion factors when using different UOMs
  - Defensive checks for stock reservation calculations

- **Stock Lookup Across Warehouses**
  - New stock lookup dialog for checking item availability across all warehouses
  - Variant selection support in warehouse availability dialog

- **Speed Enhancements**
  - Clear customer search input field on click for faster customer selection
  - Clear item search bar on click for faster item search
  - Improved search UX for high-volume POS operations

### Changed
- **Subtotal Calculation**
  - Fixed subtotal recalculation when UOM changes mid-transaction
  - Cache rebuild after UOM change ensures accurate totals

- **RTL/LTR Compatibility**
  - Fixed contradicting RTL patterns in InvoiceDetailDialog
  - Added text-start class for proper RTL text alignment in ReturnInvoiceDialog
  - Removed manual RTL overrides that prevented natural mirroring

- **Invoice Display**
  - Show actual paid amount instead of grand total in invoice confirmation
  - Enhanced InvoiceCart layout for improved alignment of financial summaries

### Fixed
- **Pay on Account & Partial Payment**
  - Improved Pay on Account and Partial Payment handling in returns
  - Fixed payment flow for credit sale returns

- **Cart Operations with UOM**
  - Remove item by UOM works correctly for multi-UOM carts
  - Update quantity targets correct item line with same item_code but different UOM
  - Quantity validation ensures positive integer values

- **Customer Selection**
  - Prevent auto-select when clearing customer search field

- **Arabic Translations**
  - Fixed truncated translation key for cart requirements message
  - Keep POS Next brand name consistent across translations
  - Fixed "Apply Coupon" and "serials" translations for clarity

## [1.10.0] - 2025-11-28

### Added
- **Comprehensive Localization System**
  - Added locale management with Arabic translations for the entire POS application
  - Implemented LanguageSwitcher component integrated into POSHeader
  - User language change API with locale management in useLocale composable
  - Translation caching with IndexedDB for improved performance
  - Dynamic translation updates ensuring components re-render with selected language
  - Page reload mechanism to apply new translations consistently
  - Translation function calls added throughout the codebase for full i18n support

- **Sales Person Feature**
  - Implemented sales person selection and allocation in payment dialog
  - Sales person tracking in invoice processing for commission management

- **Enhanced Stock Validation**
  - Improved stock validation and item handling in cart and selection dialogs
  - Better error handling for stock-related operations

### Changed
- **RTL/LTR Support Improvements**
  - Enhanced RTL support for TextInput components with better layout alignment
  - Improved InvoiceDetailDialog RTL/mobile support with currency formatting
  - Standardized invoice status colors for both LTR and RTL layouts
  - Fixed RTL support for resizing behavior in POSSale component
  - Adjusted cache tooltip positioning and styling for RTL direction in POSHeader

- **Language Switcher UX**
  - Moved language switcher to user menu on mobile for a more compact header
  - Improved button and dropdown styles for better UI consistency

- **Serial Number Management**
  - Enhanced serial number management in POS for better tracking and selection

- **Layout and Spacing Improvements**
  - Refactored layout and spacing across UserMenu, POSHeader, ItemsSelector, and POSSale components
  - Improved overall UI consistency throughout the application

### Fixed
- **Dependency Updates**
  - Fixed frappe-ui dependency version format in package.json

- **POS Settings Configuration**
  - Removed problematic autoname field from POS settings configuration

- **Arabic Translations**
  - Updated Arabic translations for improved clarity and accuracy
  - Enhanced Arabic translations for invoices and item sorting functionality

## [1.9.0] - 2025-11-23

### Added
- **Country Code Selector for Customer Phone Numbers**
  - Added country code selector with flag icons for customer phone input
  - Visual country flag display for better user experience
  - Support for international phone number formats
- **Invoice Detail View**
  - Implemented comprehensive invoice detail view with proper API endpoints
  - Enhanced invoice information display and navigation
- **User Profile Management**
  - Added user profile image display in POS header
  - Implemented reactive user data management system
  - Real-time user information updates

### Changed
- **Print Functionality**
  - Updated print endpoint to use printview for better browser compatibility
  - Improved cross-browser printing experience
- **Node.js Version Update**
  - Updated Node.js version to 20 in CI workflow for better performance and security

### Fixed
- **Warehouse Availability Check**
  - Added warehouse availability check for out-of-stock items
  - Prevents selection of items not available in selected warehouse
- **Disabled Items Filtering**
  - Filter disabled items from Items Selector and search results
  - Only show active items available for sale
- **Customer API**
  - Fixed indentation in customer API for better code readability
  - Load all customers without hardcoded limit for better scalability
- **Return Invoice Dialog**
  - Enhanced return invoice dialog layout and status display
  - Adjusted dialog sizes for better UX across different screen sizes
  - Improved mobile responsiveness for return invoice dialog
- **Shift Dialog Navigation**
  - Navigate to POSSale when shift dialog is closed via X button
  - Better user flow when dismissing shift dialog
- **User Authentication Race Condition**
  - Resolved race condition where user appears as Guest after login
  - Fixed authentication state synchronization issues
- **Automatic Offer Validation**
  - Added automatic offer validation and removal when cart conditions change
  - Ensures promotional offers remain valid based on current cart state
- **Login Error Messages**
  - Show descriptive error message when inputting wrong credentials
  - Navigate to /pos when clicking cancel button of ShiftDialog

### Improved
- **Return Invoice UI**
  - Extracted payment icon utility for better code reusability
  - Improved return invoice UI consistency and styling
- **Cart UX Improvements**
  - **Customer Section:**
    - Added quick customer creation button next to search input
    - Large touch-friendly button (44px+) with user-plus icon
    - Improved search input with better sizing and rounded corners
    - Professional customer card design with gradient avatar
  - **Empty Cart Quick Actions:**
    - Implemented 2x3 grid with 6 action buttons
    - Quick access to: View Shift, Draft Invoices, Invoice History, Return Invoice, Close Shift, Create Customer
    - Icon backgrounds with subtle hover effects
    - Touch-friendly sizing meeting accessibility standards
  - **Cart Items Section:**
    - Relocated Offers & Coupon buttons to dedicated section below customer bar
    - Larger buttons with improved styling and badge visibility
    - Better spacing and padding throughout
  - **Action Buttons:**
    - Checkout and Hold Order now side-by-side (50/50 width)
    - Saves ~70px vertical space for more cart visibility
    - Consistent sizing and rounded styling
  - **Touch & Mobile Improvements:**
    - All buttons meet 44px+ minimum touch target
    - Increased padding and better text sizes
    - Consistent rounded styling and proper hover/active states

### Removed
- **POS Profile Feature Cleanup**
  - Removed create_pos_invoice_instead_of_sales_invoice feature from POS Profile
  - Simplified POS Profile configuration

## [1.8.0] - 2025-11-17

### Added
- **User-Controlled Sorting UI**
  - Added interactive sort dropdown with adjustments icon next to view controls
  - Toggle-based sorting: click to cycle between ascending/descending/none
  - Sort by name, quantity, item group, price, and item code
  - Visual feedback with active state icons and tooltips
  - Conditional sorting: only sorts when user explicitly triggers
  - Easy to extend with new sort fields
- **First/Last Page Navigation**
  - Added First/Last page navigation buttons to both grid and list views
  - First button (« on mobile) jumps to page 1
  - Last button (» on mobile) jumps to last page
  - Buttons disabled when already on first/last page

### Changed
- **Payment Methods Preloading**
  - Payment methods now always load at application startup
  - Ensures payment modes are available for offline mode
  - Removed conditional cache check that could skip loading
  - Added comprehensive logging for payment methods caching
  - Better offline reliability for payment processing

### Fixed
- **Payment Dialog UX Improvements**
  - Fixed payment amount increment step from 0.01 to 5 for better user experience
  - Changed increment applies to both payment entry inputs and custom amount fields
  - More logical increments for typical payment amounts
- **Payment Dialog Layout**
  - Fixed button alignment in payment dialog footer
  - All action buttons now appear on the same row
  - "Clear All" button positioned on left, action buttons on right
  - Improved visual consistency and professional appearance
- **Print Format Discount Display**
  - Fixed print format condition to handle negative discount_amount values
  - Changed condition from `> 0` to checking if discount exists
  - Added absolute value filter for correct display regardless of sign
  - Fixed issue where Frappe's print pipeline negates discount_amount causing display failure
- **Pagination Display Logic**
  - Fixed "All items loaded" message to only show on last page or when all items fit in one page
  - Previously showed incorrectly on first page
- **Browser Compatibility**
  - Fixed "crypto.randomUUID is not a function" error in POS Events Store
  - Implemented multi-tier UUID generation strategy for older browsers
  - RFC4122 v4 compliant fallback using Crypto API and Math.random()
  - Support for globalThis, window.crypto, and legacy environments

### Improved
- **Shift Closing Dialog Performance & Accessibility**
  - Fixed hideExpectedAmount reactivity bug using storeToRefs
  - Added comprehensive prop validation with type checking
  - Converted template function calls to computed properties for better performance
  - Extracted complex nested conditions to readable computed properties
  - Added ARIA labels for screen readers and keyboard navigation
  - Improved error handling with user-friendly messages and dismiss action
  - Added loading states and input validation
- **Item Sorting Implementation**
  - Refactored from 265 lines of repetitive code to 78 lines using v-for loop
  - 70% code reduction in dropdown implementation
  - Extracted sort configuration into SORT_OPTIONS and SORT_ICONS constants
  - O(n log n) sorting only on user action, not every render
  - Improved maintainability: new sort options require single array entry
- **Quantity-Based Sorting**
  - Items sorted by stock quantity in descending order (highest first)
  - Out-of-stock items automatically move to the bottom
  - Uses JavaScript's native Timsort algorithm for optimal performance
  - O(n log n) worst case, O(n) best case for nearly-sorted data
  - Performance: 100 items ~1ms, 500 items ~3ms, 1000 items ~5ms
  - Works for regular stock items and Product Bundles
- **Bundle Stock Display**
  - Show stock badge only for stock items and bundles
  - Display "N/A" for non-stock items in list view
  - Add bundle-specific UOM label in tooltips
  - Skip validation for batch/serial items (handled in dialog)
  - Differentiate error messages between bundles and regular items

## [1.7.1] - 2025-11-13

### Added
- **Workspace Reinstallation Migration**
  - Added migration hook to automatically reinstall workspace with latest configuration
  - Dynamic auto-discovery of all workspace JSON files in the workspace directory
  - Ensures workspace updates are applied during app upgrades
  - Comprehensive error handling and logging for workspace operations
- **Community Support Enhancement**
  - Added Telegram community link for real-time user communication and support
  - Reorganized Support & Community section in README for better visibility

### Fixed
- **Workspace Configuration**
  - Resolved workspace URL link validation error
  - Removed problematic Start POS URL link from workspace links section
  - URL links now properly supported only in shortcuts section

## [1.7.0] - 2025-11-11

### Added
- **Proactive Filter-Aware Caching with Real-time Sync**
  - Filter-aware caching strategy that checks POS Profile item group filters before loading
  - Fetches and caches ONLY items from filtered groups (90% reduction in data transfer)
  - Real-time cache synchronization via Socket.IO when POS Profile changes
  - Smart delta calculation for surgical cache updates (added/removed groups)
  - No manual cache clearing or page reload required
  - Transaction batching in offline worker (10x performance boost)
  - Query result caching with LRU eviction (5x faster repeated queries)
  - Index-optimized IndexedDB operations
  - Circuit breaker pattern for fault tolerance with exponential backoff retry
- **Free Items Support for Promotional Offers**
  - Added processFreeItems() to handle free item quantities from backend
  - Display free item badge (+X FREE) in cart UI
  - Include free items in total quantity count
  - Minimum quantity validation for offer eligibility
  - Reactive offer eligibility based on cart changes
- **Professional Documentation Enhancement**
  - Added 5 high-quality screenshots showcasing POS features
  - Created animated sales cycle GIF demonstrating complete workflow
  - Enhanced README with visual elements and comprehensive documentation

### Fixed
- **Item Group Filter and Toast Notifications**
  - Fixed empty items display when updating item group filters
  - Added forceServerFetch parameter to bypass cache and fetch fresh data
  - Migrated from frappe-ui toast to custom useToast composable
  - Reduced notification noise by removing low-value success notifications
  - Kept critical error and warning notifications only
- **IndexedDB and Caching Issues**
  - Fixed item_prices IndexedDB constraint violations
  - Added default "Standard" price_list for items missing one
  - Graceful error handling with individual record recovery
  - Fixed Dexie transaction API syntax

### Changed
- **Offers Module Refactoring**
  - Refactored offers.py with type hints and data classes
  - Removed unused coupon functions and pos_offer references
  - Fixed database column checks in promotions.py

## [1.6.1] - 2025-11-08

### Fixed
- **Tax-Inclusive Calculation**
  - Fixed issue where tax amounts were incorrectly shown as discounts in tax-inclusive mode
  - Frontend now sends correct gross amount (after discount, before tax extraction) to ERPNext
  - Proper tax calculation based on included_in_print_rate flag
  - Fixed both scenarios: items without discounts and items with discounts

## [1.6.0] - 2025-11-07

### Added
- **Overdue Invoice Status Support**
  - Added Overdue status filter with warning icon in Invoice Management
  - Overdue invoices now clearly identified with red styling
  - Separate filter button for quick access to overdue invoices
  - Added Overdue status to invoice filters component
- **Payment Source Audit Trail**
  - Payment history now shows source (POS vs Back Office) for better tracking
  - Differentiate between POS-created payments and back-office Payment Entries
  - Enhanced payment cards with color-coded source labels (blue for Back Office)
  - Added posting date to payment history for complete audit trail

### Changed
- **Time and Date Formatting**
  - Improved time formatting to handle both Date objects and time strings (HH:MM:SS format)
  - Standardized date format to DD/MM/YY across all invoice displays
  - Enhanced `formatTime()` composable with better string parsing
  - Added comprehensive JSDoc documentation for formatter functions
- **Status Display Refactoring**
  - Consolidated status display with reusable helper functions (`getStatusLabel`, `getStatusClass`)
  - Consistent status styling across all invoice components
  - Status labels now use proper terminology ("Partially Paid" instead of "Partly Paid")

### Improved
- **Backend Performance & Architecture (partial_payments.py)**
  - **Critical N+1 Query Fix**: Reduced payment history queries from O(n) to O(1) using batch fetching
  - **48x Performance Improvement**: Optimized invoice list loading with batch queries
  - Added company filter to Payment Ledger queries for multi-company performance (10-100x faster)
  - Implemented optional metadata fetching for 2x faster dashboard views
  - SQL queries now use COALESCE for NULL safety and proper aggregation
- **Security & Validation**
  - Comprehensive input validation on all API endpoints
  - POS Profile and Mode of Payment existence validation
  - String length limits to prevent DoS attacks
  - Query limit caps to prevent resource exhaustion (max 500 invoices)
  - Payment account validation before Payment Entry creation
- **Business Logic Validations**
  - Payment date cannot be before invoice date
  - Invoice state validation (submitted, not cancelled)
  - Total payment amount validation across multiple payments
  - Currency consistency checks
  - Amount tolerance for floating-point comparisons (0.01)
- **Error Handling & Reliability**
  - Transactional rollback for atomic payment operations
  - Automatic cancellation of partially-created payments on failure
  - Structured error logging with full context for debugging
  - Graceful degradation when payment metadata unavailable
  - Missing Payment Entry detection and logging
- **Code Quality & Maintainability**
  - Added constants and Enum for configuration (PaymentSource, AMOUNT_TOLERANCE, limits)
  - Comprehensive documentation with docstrings for all functions
  - Full type hints throughout Python API (typing.Dict, List, Optional)
  - Inline comments explaining business logic and ERPNext concepts
  - Performance notes for critical operations
  - Usage examples in docstrings

### Technical Details
- Payment Ledger now used as single source of truth for all payment tracking
- Batch fetching eliminates N+1 query problem in `get_payment_history()`
- Added `include_metadata` parameter for performance optimization
- Error recovery with automatic rollback on Payment Entry creation failure
- Module docstring with architecture explanation and best practices

### Performance Metrics
- Payment history for invoice with 10 payments: 21 queries → 3 queries (7x faster)
- Load 50 partial invoices: 2,550+ queries → 53 queries (48x faster)
- Summary statistics: O(n) → O(1) (constant time)
- Multi-company Payment Ledger query: 100x+ faster with proper indexing

## [1.5.0] - 2025-11-06

### Added
- **Default Customer Auto-Loading**
  - New `get_default_customer` API endpoint in POS Profile
  - Automatically loads default customer when POS opens if configured in POS Profile
  - Customer appears in cart immediately without manual selection
  - Maintains proper customer object structure matching manual selection

### Fixed
- **Original Price Display in Receipts and UI**
  - Fixed discount handling to preserve original `price_list_rate` in both UI and created invoices
  - Receipts now clearly show: quantity × original price = subtotal, then discount line, then final total
  - Backend receives correct net rate for accurate invoice totals
  - Print format updated to 80mm thermal receipt size instead of A4
  - Discount percentages now display with 2 decimal precision (was showing many decimal places)
  - Added comprehensive JSDoc documentation for pricing and discount calculation logic

### Changed
- **Dependency Version Pinning**
  - Pinned Vue version to exact 3.5.13 (removed caret) for better stability and reproducible builds

### Improved
- **Edit Item Dialog Decimal Quantity Support**
  - Quantity field now accepts decimal values (e.g., 0.5, 1.25, 2.75) matching cart behavior
  - Added smart step increment/decrement based on current quantity value
  - Improved input handling allowing free editing with validation only on blur
  - Supports very small quantities down to 0.0001
  - Added mobile-friendly decimal keyboard input mode
- **Currency Formatting in Edit Item Dialog**
  - Replaced raw currency codes (SAR, EGP, etc.) with proper currency symbols
  - All amounts now use consistent formatCurrency utility across the dialog
  - Rate field prefix displays currency symbol instead of code
  - Subtotal, discount, and total now properly formatted with locale support

## [1.4.0] - 2025-11-06

### Fixed
- **Item Query Function Whitelisting**
  - Fixed "Function not whitelisted" error when adding Tax Rules
  - Added `@frappe.whitelist()` decorator to `item_query` function
  - Parse JSON filters parameter when called from frontend
  - Remove mandatory company validation to allow global items
  - Set `custom_company` to empty string for new items without company
  - Fix demo data setup which creates items without company
  - Enabled global item selection across POS profiles
- **Mobile UI Layout**
  - Make footer fixed at bottom to prevent scrolling issues on mobile
  - Add responsive column widths to list view for better mobile experience
  - Fix vertical scrolling in ItemsSelector with proper min-height constraints
  - Move status messages inside table rows to span full width
  - Adjust floating cart button position to sit above fixed footer
  - Optimize column sizing: mobile (120px name, 70px rate/qty), tablet (180px), desktop (200px)

## [1.3.0] - 2025-11-05

### Added
- **BrainWise Branding API**
  - Implemented secure branding configuration API with validation
  - Centralized branding management system
- **POS Profile Custom Fields**
  - Added "Cash Mode of Payment" field to specify default cash payment method
  - Added "Block Sale Beyond Available Qty" field for stock control
  - Added "Allow Delete Draft Invoices" field for draft management permissions
- **Saudi Riyal Font Support**
  - Updated CSS to properly render Saudi Riyal currency symbol (ر.س)
  - Improved font rendering for Arabic text

## [1.2.0] - 2025-11-04

### Added
- **CSRF Token Synchronization**
  - Implemented CSRF token sync with offline worker for enhanced security
  - Ensures secure API calls from background workers
- **POSNext Workspace Configuration**
  - Added workspace links for enhanced navigation
  - Improved accessibility to POS features

### Changed
- **Project Documentation**
  - Updated project references for clarity and consistency
  - Improved inline documentation across codebase

### Fixed
- **Cart Data Processing**
  - Use `toRaw()` to prevent stale cached quantities in invoice data
  - Ensures fresh data is always used in calculations
- **Header Layout**
  - Removed `overflow-x-hidden` class from POSHeader for improved responsiveness

## [1.1.1] - 2025-10-29

### Added
- **Payment Dialog: Customer Credit/Outstanding Balance Display**
  - Real-time customer balance display with color-coded indicators
  - Green indicator for available credit
  - Red indicator for outstanding balance (amount owed)
  - Gray indicator for zero balance
  - Comprehensive balance information showing total outstanding, total credit, and net position
- **New API Endpoint: `get_customer_balance`**
  - Returns detailed customer balance including total outstanding, total credit, and net balance
  - Calculates from Sales Invoices and Payment Entries
  - Supports company-specific filtering
- **Payment Dialog: Dynamic Button States**
  - "Pay on Account" button automatically disables when payment entries are added
  - Button re-enables when all payments are removed
  - Prevents mixing regular payments with credit sales

### Changed
- **Payment Dialog Layout Reorganization**
  - Information section moved to top (payment summary, customer credit, discount, payment breakdown)
  - All payment action buttons consolidated at bottom
  - Clear visual separation between information and actions
  - "Pay on Account" button matches "Complete Payment" button styling
  - Button color scheme changed to warm orange tones (orange-600 enabled, orange-400 disabled)
- **Customer Credit Display**
  - Now fetches both available credit sources and overall balance
  - Shows comprehensive credit position instead of just available credit
  - Displays appropriate message based on balance status
- Payment action buttons positioned in dialog footer for better UX

### Fixed
- **Critical: Double discount bug** - Discounts were being applied twice (once in item rate, once in total calculation)
  - Frontend now correctly uses `price_list_rate` for subtotal calculations
  - Backend reverse-calculates `price_list_rate` from discounted rate to prevent double application
  - Example: Item with 10% discount now correctly shows 90.00 instead of 81.00
- **Customer credit not displaying correctly** - Credit was only showing available credit, not outstanding balance
- **"Disable Rounded Total" setting not working** - Backend was checking POS Profile instead of POS Settings
- **ReferenceError: couponCode is not defined** - Fixed undefined couponCode error in posCart.js when re-applying offers
  - Changed reference from non-existent `couponCode.value` to `appliedCoupon.value?.name`
- Subtotal calculation now uses original price before discount (fixes display inconsistency)
- "Pay on Account" button styling now matches other action buttons

### Improved
- Improved discount calculation logic with comprehensive documentation
- Added validation to prevent invalid discount percentages (now clamped to 0-100%)
- Enhanced error handling for rounding setting retrieval
- Added data integrity checks (price_list_rate must be >= rate)
- Added detailed inline documentation for discount calculation flow
- Code cleanup with better comments explaining critical logic
- Separated discount calculation into clearly documented sections
- Payment dialog now provides clearer visual feedback for button states

## [1.1.0] - 2025-10-28

### Added
- Real-time settings updates without page reload using Pinia event system
- Event-driven architecture for settings changes (pricing, sales operations, display)
- Missing fields to POS Settings DocType: `allow_user_to_edit_item_discount` and `disable_rounded_total`
- Settings event listeners in POSSale component for immediate UI updates
- Display settings change detection and event emission
- Toast notifications for settings changes to provide user feedback
- Comprehensive CHANGELOG.md following Keep a Changelog format

### Changed
- Settings now update immediately in all components without requiring page refresh
- POS Settings store now includes `reloadSettings()` method for forced refresh
- Event detection system now includes all pricing and display fields

### Fixed
- "Allow Item Discount" setting not persisting to database
- "Disable Rounded Total" setting not persisting to database
- Settings reverting to defaults after page refresh

## [1.0.2] - 2025-10-28

### Added
- App version display in POS header with enhanced styling
- UOM pricing logic with conversion factor support

### Changed
- Enhanced POS header to display current application version
- Updated UOM pricing calculations to account for conversion factors

## [1.0.1] - 2025-10-27

### Added
- Invoice filtering logic and store management
- Partial Payments feature in POS
- Stock validation and event-driven settings management
- Word-order independent search for cached items
- Referral code management with validation and coupon generation
- Fuzzy word-order independent item search
- Periodic stock sync functionality
- Performance optimizations for low-end devices
- Developer tooling for debugging

### Changed
- Improved search functionality with fuzzy matching and relevance scoring
- Enhanced offline mode and UI responsiveness
- Optimized ItemsSelector component for better performance
- Improved list view functionality

### Fixed
- Stock badge synchronization issue
- Stock reservations preservation during refresh
- Warehouse change detection
- Logger.success error in Web Worker context
- High-priority performance and memory issues

## [1.0.0] - Initial Release

### Added
- Core POS functionality
- Offline mode support
- Invoice management
- Customer management
- Item search and selection
- Payment processing
- Shift management
- Stock tracking

[Unreleased]: https://github.com/BrainWise-DEV/POSNext/compare/v1.13.0...HEAD
[1.13.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.12.0...v1.13.0
[1.12.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.11.0...v1.12.0
[1.11.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.10.0...v1.11.0
[1.10.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.7.1...v1.8.0
[1.7.1]: https://github.com/BrainWise-DEV/POSNext/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.6.1...v1.7.0
[1.6.1]: https://github.com/BrainWise-DEV/POSNext/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/BrainWise-DEV/POSNext/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/BrainWise-DEV/POSNext/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/BrainWise-DEV/POSNext/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/BrainWise-DEV/POSNext/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/BrainWise-DEV/POSNext/releases/tag/v1.0.0
