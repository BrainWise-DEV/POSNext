import { computed, ref, watch, nextTick, onUnmounted } from "vue";
import { QueuedMutex } from "@/utils/mutex";

/**
 * Composable for search input, barcode scanning, and auto-add logic.
 *
 * Owns all search-input state, timers, and event handlers with proper
 * concurrency control.  Extracted from ItemsSelector.vue.
 *
 * Concurrency model:
 *   - On Enter (or auto-add timeout), the barcode is **snapshotted** from the
 *     DOM input immediately, then the input is cleared so the next scan starts
 *     into a clean field.
 *   - The snapshot is pushed into a {@link QueuedMutex}-backed queue
 *     (`processBarcodeScan`), which processes barcode lookups sequentially.
 *   - This guarantees no barcode is ever lost, even when scanning different
 *     items faster than the API can respond (~50 ms between scans).
 *   - The visible results are snapshotted with the barcode, so a name search
 *     that misses as a barcode can still add its single visible result.
 *
 * @param {Object} options
 * @param {Object} options.itemStore          - Pinia item-search store
 * @param {(item: Object, autoAdd: boolean) => boolean} options.onItemFound
 *        Component's selectItem(). Returns true if item was accepted.
 * @param {Object} options.showWarning        - useToast().showWarning
 * @param {import('vue').Ref<boolean>} options.isAnyDialogOpen
 */
export function useSearchInput({ itemStore, onItemFound, showWarning, isAnyDialogOpen }) {
	// --- Reactive state (exposed) ---
	const searchInputRef = ref(null);
	const scannerEnabled = ref(false);
	const autoAddEnabled = ref(false);
	// Result highlighted with the arrow keys (-1 = none)
	const highlightedIndex = ref(-1);
	const highlightedCode = computed(
		() => itemStore.filteredItems?.[highlightedIndex.value]?.item_code ?? null
	);

	// --- Internal (non-reactive) ---
	let autoSearchTimer = null;
	const barcodeQueue = new QueuedMutex({ timeout: 10000, name: "BarcodeSearch" });

	// ---- Timer helpers ----

	function clearAutoSearchTimer() {
		if (autoSearchTimer) {
			clearTimeout(autoSearchTimer);
			autoSearchTimer = null;
		}
	}

	// ---- Focus ----

	function focusSearchInput() {
		nextTick(() => {
			if (searchInputRef.value) {
				searchInputRef.value.focus();
			}
		});
	}

	// ---- Clear ----

	/** Atomic clear: timer -> store -> DOM input.value -> refocus */
	function clearSearchAndResetInput() {
		clearAutoSearchTimer();
		highlightedIndex.value = -1;
		itemStore.clearSearch();
		if (searchInputRef.value) {
			searchInputRef.value.value = "";
		}
		if (scannerEnabled.value || autoAddEnabled.value) {
			focusSearchInput();
		}
	}

	// ---- Event handlers ----

	function handleKeyDown(event) {
		if (event.key === "ArrowDown" || event.key === "ArrowUp") {
			const count = itemStore.searchTerm?.trim() ? itemStore.filteredItems?.length || 0 : 0;
			if (!count) return;
			event.preventDefault();
			const step = event.key === "ArrowDown" ? 1 : -1;
			highlightedIndex.value = Math.min(count - 1, Math.max(0, highlightedIndex.value + step));
			return;
		}
		if (event.key === "Escape") {
			clearSearchAndResetInput();
			return;
		}
		if (event.key === "Enter") {
			event.preventDefault();
			clearAutoSearchTimer();

			// Snapshot the barcode and the visible results NOW, before anything overwrites them
			const barcode = searchInputRef.value?.value?.trim() || itemStore.searchTerm?.trim();
			const visibleItems = itemStore.searchTerm?.trim() ? [...(itemStore.filteredItems || [])] : [];
			const highlighted = visibleItems[highlightedIndex.value];
			if (barcode) {
				// Clear input immediately so next scan starts clean
				clearSearchAndResetInput();

				// Highlighted result: add it directly
				if (highlighted) {
					onItemFound(highlighted, false);
					focusSearchInput();
					return;
				}

				// Queue the search with the captured barcode
				processBarcodeScan(barcode, autoAddEnabled.value, visibleItems);
			}
			return;
		}
		// All other keys: no special handling needed.
		// Dead scanner-speed-detection code removed.
	}

	/**
	 * Handles the `input` event on the search <input>.
	 *
	 * Two independent timers exist by design:
	 *   1. itemStore.setSearchTerm() triggers the store's own debounce for
	 *      updating the displayed item grid.
	 *   2. autoSearchTimer (500 ms) triggers auto-add behaviour — completely
	 *      separate from display.
	 */
	function handleSearchInput(event) {
		const value = event.target.value;

		// Guard: ignore stale empty events after search was already cleared
		if (!value && !itemStore.searchTerm) {
			return;
		}

		itemStore.setSearchTerm(value);
		highlightedIndex.value = -1;

		clearAutoSearchTimer();

		// Auto-add: after user stops typing for 500 ms, trigger barcode search
		if (autoAddEnabled.value && value.trim().length > 0) {
			autoSearchTimer = setTimeout(() => {
				const barcode =
					searchInputRef.value?.value?.trim() || itemStore.searchTerm?.trim();
				if (barcode) {
					itemStore.clearSearch();
					if (searchInputRef.value) searchInputRef.value.value = "";
					processBarcodeScan(barcode, true);
				}
			}, 500);
		}
	}

	/** Clicking the search input selects its text so the next scan or typing replaces it. */
	function handleSearchClick() {
		searchInputRef.value?.select();
	}

	/**
	 * Queue a barcode scan for sequential processing.
	 *
	 * The barcode string is already captured (snapshotted) by the caller —
	 * it is never read from shared state here. The {@link QueuedMutex}
	 * ensures scans execute one at a time so every scan is resolved before
	 * the next begins, preventing double-adds and lost barcodes.
	 *
	 * Lookup: exact barcode match via `itemStore.searchByBarcode()`.
	 * If the barcode is not found, adds the single visible result; with several
	 * results it restores the query and asks the cashier to pick; otherwise
	 * shows a "not found" warning.
	 *
	 * @param {string}  barcode      - Pre-captured barcode value
	 * @param {boolean} forceAutoAdd - When true, item is added without user click
	 * @param {Array}   [visibleItems] - Results that were visible when Enter was pressed
	 */
	function processBarcodeScan(barcode, forceAutoAdd, visibleItems = []) {
		const shouldAutoAdd = forceAutoAdd || (scannerEnabled.value && autoAddEnabled.value);

		barcodeQueue.withLock(async () => {
			try {
				const item = await itemStore.searchByBarcode(barcode);
				if (item) {
					onItemFound(item, shouldAutoAdd);
					focusSearchInput();
					return;
				}
			} catch (error) {
				console.error("Barcode API error:", error);
			}

			// Barcode not found — fall back to the results snapshotted on Enter
			if (visibleItems.length === 1) {
				onItemFound(visibleItems[0], false);
				focusSearchInput();
				return;
			}
			if (visibleItems.length > 1) {
				// Restore the query unless a new scan has started
				if (!searchInputRef.value?.value && !itemStore.searchTerm) {
					itemStore.setSearchTerm(barcode);
					if (searchInputRef.value) searchInputRef.value.value = barcode;
				}
				showWarning(
					__("No barcode matches «{0}». Pick from the results or scan the barcode again.", [
						barcode,
					])
				);
				focusSearchInput();
				return;
			}
			showWarning(__("Item Not Found: No item found with barcode: {0}", [barcode]));
			focusSearchInput();
		});
	}

	// ---- Toggles ----

	function toggleBarcodeScanner() {
		scannerEnabled.value = !scannerEnabled.value;

		if (scannerEnabled.value) {
			autoAddEnabled.value = true;
			focusSearchInput();
		} else {
			autoAddEnabled.value = false;
		}
	}

	function toggleAutoAdd() {
		autoAddEnabled.value = !autoAddEnabled.value;

		if (autoAddEnabled.value && !scannerEnabled.value) {
			scannerEnabled.value = true;
		}

		if (!autoAddEnabled.value) {
			clearAutoSearchTimer();
		}

		if (autoAddEnabled.value) {
			focusSearchInput();
		}
	}

	// ---- Dialog-close watcher ----
	// Refocuses the search bar when all dialogs close (scanner/auto-add modes)
	const stopDialogWatcher = watch(isAnyDialogOpen, (isOpen, wasOpen) => {
		if (wasOpen && !isOpen && (scannerEnabled.value || autoAddEnabled.value)) {
			focusSearchInput();
		}
	});

	// ---- Cleanup ----
	function cleanup() {
		clearAutoSearchTimer();
		stopDialogWatcher();
	}

	onUnmounted(cleanup);

	return {
		// State
		searchInputRef,
		scannerEnabled,
		autoAddEnabled,
		highlightedIndex,
		highlightedCode,

		// Event handlers
		handleSearchInput,
		handleKeyDown,
		handleSearchClick,

		// Toggles
		toggleBarcodeScanner,
		toggleAutoAdd,

		// Utilities
		focusSearchInput,
		clearSearchAndResetInput,
		cleanup,
	};
}
