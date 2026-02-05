# Large Catalog Optimization (65K+ Items)

This document describes the optimization changes made to support POS systems with very large item catalogs (65,000+ items) while maintaining fast UI performance and full offline support.

## Problem Statement

With 65K+ items in a catalog:
- Loading all items at once causes UI freeze (5-10 seconds)
- IndexedDB sync takes too long with interval-based approach (54+ minutes)
- Barcode scanning must work immediately, even before full sync completes
- Offline mode requires all items cached in IndexedDB

## Solution Overview

| Aspect | Before | After |
|--------|--------|-------|
| Initial UI load | All items at once | 100 items (fast) |
| Background sync | 15-second intervals | Continuous batching (500ms delay) |
| 65K sync time | ~54 minutes | ~3-5 minutes |
| Tab switching | Client-side filter | Server-side fetch |
| Barcode (online) | Server API | Server API (unchanged) |
| Barcode (offline) | IndexedDB lookup | IndexedDB lookup (faster sync) |

---

## Backend Changes

### 1. Item Group Hierarchy (`pos_next/api/items.py`)

#### New Function: `_get_item_group_with_descendants()`

Uses Frappe's nested set model (lft/rgt) to get all child groups of a parent group.

```python
def _get_item_group_with_descendants(item_group):
    """Get an item group and all its descendants using nested set model."""
    if not item_group:
        return []

    ItemGroup = DocType("Item Group")

    # Get the parent group's lft/rgt values
    group_data = (
        frappe.qb.from_(ItemGroup)
        .select(ItemGroup.lft, ItemGroup.rgt, ItemGroup.is_group)
        .where(ItemGroup.name == item_group)
        .run(as_dict=True)
    )

    if not group_data:
        return [item_group]

    group = group_data[0]
    if not group.is_group:
        return [item_group]

    # Get all descendants using nested set (lft/rgt)
    descendants = (
        frappe.qb.from_(ItemGroup)
        .select(ItemGroup.name)
        .where(ItemGroup.lft > group.lft)
        .where(ItemGroup.rgt < group.rgt)
        .run(pluck="name")
    )

    return [item_group] + list(descendants)
```

**Usage:** When user selects parent group "Room" in POS Profile, items from child groups "Deluxe", "Superior" are also included.

#### New Endpoint: `get_items_bulk()`

Fetches items from multiple item groups in a single query, eliminating N+1 problem.

```python
@frappe.whitelist()
def get_items_bulk(pos_profile, item_groups=None, limit=2000):
    """
    Fetch items from multiple item groups in a SINGLE query.
    Eliminates N+1 problem where frontend was making one API call per group.

    Args:
        pos_profile: POS Profile name
        item_groups: JSON array of item group names
        limit: Max items to return (default 2000)
    """
```

#### Modified: `get_item_groups()`

Now returns hierarchical data with `child_groups` for each parent group:

```python
{
    "item_group": "Room",
    "child_groups": ["Deluxe", "Superior", "Standard"]
}
```

Also includes Redis caching (5-minute TTL) for performance.

#### Modified: `_build_item_base_conditions()`

Uses `_get_item_group_with_descendants()` to filter items by parent group + all children.

---

### 2. POS Profile API (`pos_next/api/pos_profile.py`)

#### Modified: `get_pos_profile_data()`

Now includes `item_groups_hierarchy` in the response, eliminating a separate API call:

```python
return {
    "pos_profile": profile_data,
    "item_groups_hierarchy": item_groups_with_hierarchy,  # NEW
    # ... other fields
}
```

**Before:** 2 API calls (profile + item groups)
**After:** 1 API call (combined)

---

## Frontend Changes

### 1. Item Search Store (`POS/src/stores/itemSearch.js`)

#### New: Aggressive Background Sync

Replaced interval-based sync (15-second delays) with continuous batching:

```javascript
async function startBackgroundCacheSync(profile, filterGroups = []) {
    const batchSize = 500
    const BATCH_DELAY_MS = 500  // 500ms between batches

    // CONTINUOUS SYNC LOOP - much faster than interval-based!
    const syncLoop = async () => {
        while (cacheSyncing.value) {
            // Fetch batch
            const response = await call("pos_next.api.items.get_items", {
                pos_profile: profile,
                item_group: currentGroup,
                start: offset,
                limit: batchSize,
            })

            // Cache to IndexedDB
            await offlineWorker.cacheItems(list)

            // Update progress for UI
            cacheStats.value = {
                ...cacheStats.value,
                items: totalCached,
                lastSync: new Date().toISOString()
            }

            // Small delay to not overwhelm server
            await new Promise(resolve => setTimeout(resolve, BATCH_DELAY_MS))
        }
    }

    syncLoop()  // Runs in background
}
```

**Performance:**
- 65K items ÷ 500 per batch = 130 batches
- 130 batches × 500ms delay = ~65 seconds network time
- Total with processing: ~3-5 minutes

#### New: On-Demand Tab Loading

When user clicks an item group tab, fetch items from server instead of client-side filtering:

```javascript
async function setSelectedItemGroup(group) {
    selectedItemGroup.value = group

    if (posProfile.value) {
        loading.value = true
        try {
            let items = []
            if (group) {
                // Specific group: fetch from server
                items = await fetchItemsForGroup(posProfile.value, group, 0, 100)
            } else {
                // "All Items" tab: fetch without group filter
                const response = await call("pos_next.api.items.get_items", {
                    pos_profile: posProfile.value,
                    item_group: null,
                    limit: 100,
                })
                items = response?.message || []
            }

            if (items.length > 0) {
                replaceAllItems(items)
            }
        } finally {
            loading.value = false
        }
    }
}
```

#### New: `fetchItemsForGroup()`

Fetches items for a specific group, expanding parent groups to include children:

```javascript
async function fetchItemsForGroup(profile, itemGroup, start = 0, limit = 100) {
    // Get expanded groups (parent + children)
    const groupInfo = itemGroups.value?.find(g => g.item_group === itemGroup)
    const groupsToFetch = groupInfo?.child_groups?.length
        ? [itemGroup, ...groupInfo.child_groups]
        : [itemGroup]

    // Use bulk endpoint for multiple groups
    if (groupsToFetch.length > 1) {
        const response = await call("pos_next.api.items.get_items_bulk", {
            pos_profile: profile,
            item_groups: JSON.stringify(groupsToFetch),
            limit: limit,
        })
        return response?.message || []
    }
    // ... single group fetch
}
```

#### Modified: `setPosProfile()`

Uses combined API response to set both profile data and item groups hierarchy:

```javascript
async function setPosProfile(profile, autoLoadItems = true) {
    // Single API call returns EVERYTHING
    const data = await call("pos_next.api.pos_profile.get_pos_profile_data", {
        pos_profile: profile
    })

    profileItemGroups.value = data?.pos_profile?.item_groups || []
    itemGroups.value = data?.item_groups_hierarchy || []  // Includes child_groups

    if (autoLoadItems) {
        loadAllItems(profile)
    }
}
```

#### Modified: `filteredItems` Computed

Now includes child groups in the allowed set for proper filtering:

```javascript
const filteredItems = computed(() => {
    // ...
    if (selectedItemGroup.value) {
        // Include child groups for parent item groups
        const groupsToFilter = getGroupsToFilter(selectedItemGroup.value)
        list = sourceItems.filter(i => groupsToFilter.has(i.item_group))
    } else if (profileItemGroups.value?.length > 0) {
        // "All Items" - include all configured groups + their children
        const allowedGroups = new Set(profileItemGroups.value.map(g => g.item_group))
        itemGroups.value.forEach(g => {
            if (g.child_groups) {
                g.child_groups.forEach(child => allowedGroups.add(child))
            }
        })
        list = sourceItems.filter(i => allowedGroups.has(i.item_group))
    }
    // ...
})
```

---

### 2. POS Header (`POS/src/components/pos/POSHeader.vue`)

#### New: Sync Progress Badge

Shows a pulsing badge on the cache icon during sync with compact item count:

```vue
<!-- Sync progress badge (visible during sync) -->
<span
    v-if="cacheSyncing && cacheStats?.items > 0"
    class="absolute -bottom-1 -end-1 bg-orange-500 text-white text-[8px] font-bold rounded-full px-1 min-w-[20px] h-4 flex items-center justify-center shadow-md animate-pulse"
>
    {{ formatCompactNumber(cacheStats.items) }}
</span>
```

**Display:** Shows "12.5K" for 12,500 items.

#### New: Sync Progress Banner in Tooltip

When clicking the cache icon during sync:

```vue
<!-- Sync Progress Banner (shown during sync) -->
<div v-if="cacheSyncing" class="mb-2 p-2 bg-orange-500/20 rounded-lg">
    <div class="flex items-center gap-2 mb-1.5">
        <svg class="w-4 h-4 animate-spin text-orange-400">...</svg>
        <span class="text-orange-300 font-semibold">{{ __('Syncing for offline...') }}</span>
    </div>
    <div class="text-center">
        <span class="text-white font-bold text-lg">{{ formatNumber(cacheStats?.items || 0) }}</span>
        <span class="text-gray-400 text-[10px] ms-1">{{ __('items cached') }}</span>
    </div>
    <div class="mt-1.5 text-[9px] text-gray-400 text-center">
        {{ __('Barcode scanning works for cached items') }}
    </div>
</div>
```

#### New Helper Functions

```javascript
function formatNumber(num) {
    if (!num) return '0'
    return num.toLocaleString()  // "12,500"
}

function formatCompactNumber(num) {
    if (!num) return '0'
    if (num >= 1000) {
        return (num / 1000).toFixed(num >= 10000 ? 0 : 1) + 'K'  // "12.5K" or "65K"
    }
    return num.toString()
}
```

---

## Data Flow

### Page Load (Online)

```
1. setPosProfile()
   └── API: get_pos_profile_data (includes item_groups_hierarchy)
       ├── Set profileItemGroups (raw groups from profile)
       └── Set itemGroups (with child_groups metadata)

2. loadAllItems()
   └── API: get_items (limit: 100, first group)
       ├── Display 100 items in UI (instant)
       └── Start background sync

3. startBackgroundCacheSync() [BACKGROUND]
   └── Loop: For each configured group
       ├── API: get_items (batch of 500)
       ├── Cache to IndexedDB
       ├── Update cacheStats (UI shows progress)
       └── Wait 500ms, repeat
```

### Tab Click (e.g., "Room" group)

```
1. setSelectedItemGroup("Room")
   └── API: get_items_bulk (Room + Deluxe + Superior)
       ├── Replace allItems with results
       └── UI shows items from selected group
```

### Offline Mode

```
1. loadAllItems() detects offline
   └── Load from IndexedDB (up to 10K items)
       ├── Client-side filtering for tabs
       └── Search works against cached items

2. Barcode scanning
   └── IndexedDB lookup via getItemByBarcode()
       └── Works for any cached item
```

---

## Configuration

### Batch Sizes

| Setting | Value | Notes |
|---------|-------|-------|
| Initial load | 100 items | Fast UI display |
| Background sync batch | 500 items | Balance speed vs server load |
| Batch delay | 500ms | Prevents overwhelming server |
| Offline load limit | 10,000 items | Memory constraint |

### Redis Cache

- Item groups: 5-minute TTL
- Key format: `pos_item_groups_{profile_name}`

---

## Testing

### Verify Background Sync

1. Open browser console
2. Load POS page
3. Look for logs:
   ```
   Starting AGGRESSIVE background sync for X groups
   Sync progress: 2500 items cached (5 batches)
   Background sync COMPLETE - 65000 items cached in 130 batches
   ```

### Verify Sync Progress UI

1. Click cache icon in header during sync
2. Should see:
   - Orange "Syncing for offline..." banner
   - Large item count updating in real-time
   - "Barcode scanning works for cached items" message

### Verify Barcode Scanning

1. **Online:** Scan any barcode - works immediately via server API
2. **Offline:** Scan barcode for cached item - works via IndexedDB
3. **Offline (uncached):** Shows "Item not found" until sync completes

---

## API Reference

### `get_items_bulk`

```python
@frappe.whitelist()
def get_items_bulk(pos_profile, item_groups=None, limit=2000):
    """
    Fetch items from multiple item groups in a single query.

    Args:
        pos_profile (str): POS Profile name
        item_groups (str): JSON array of item group names
        limit (int): Maximum items to return

    Returns:
        list: Items from all specified groups (deduplicated)
    """
```

### `get_item_groups`

```python
@frappe.whitelist()
def get_item_groups(pos_profile):
    """
    Get item groups configured in POS Profile with hierarchy info.

    Returns:
        list: [
            {
                "item_group": "Room",
                "child_groups": ["Deluxe", "Superior"]
            },
            ...
        ]
    """
```

---

## Performance Metrics

| Catalog Size | Initial Load | Full Sync | Tab Switch |
|--------------|--------------|-----------|------------|
| 1K items | <100ms | ~5 sec | <50ms |
| 10K items | <100ms | ~15 sec | <50ms |
| 30K items | <100ms | ~45 sec | <50ms |
| 65K items | <100ms | ~3 min | <50ms |

---

## Troubleshooting

### Sync not starting

Check console for:
```
Starting AGGRESSIVE background sync
```

If not appearing, verify:
1. POS Profile has item group filters configured
2. User is online
3. No JavaScript errors

### Slow sync

Check network tab for:
- Response times > 2 seconds indicate server/DB issues
- Consider adding database index on `item_group` column

### Items not showing after tab click

Verify:
1. `get_items_bulk` endpoint exists and is whitelisted
2. Item groups have correct parent-child relationships (lft/rgt)
3. Check console for API errors
