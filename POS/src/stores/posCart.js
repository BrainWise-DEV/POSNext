import {
	allowsAutoDiscountStacking,
	getProductStrategyForOffer,
	getStrategyForOffer,
	offerStrategyOrder,
} from "@/utils/offerStrategies";
import { useInvoice } from "@/composables/useInvoice";
import {
	COUPON_DISCOUNT_SOURCE,
	fixedCouponLineDiscount,
	hasFixedCouponDiscount,
	isCouponLine,
	preCouponDiscount,
	restorePreCouponDiscount,
	stashPreCouponDiscount,
} from "@/utils/couponLines";
import { getPrecision, roundCurrency } from "@/utils/currency";
import { usePOSOffersStore } from "@/stores/posOffers";
import { usePOSSettingsStore } from "@/stores/posSettings";
import { usePOSShiftStore } from "@/stores/posShift";
import { parseError } from "@/utils/errorHandler";
import {
	shouldValidateItemStock,
	checkStockAvailability,
	getCartStockQtyForItem,
	rowStockQty,
} from "@/utils/stockValidator";
import {
	resolveFreeItemMinQty,
	syncCartFreeItems,
	withCarvedQtyRestored,
} from "@/utils/gwpSameItemFreeRows";
import { offlineState } from "@/utils/offline/offlineState";
import { generateOfflineId } from "@/utils/offline/uuid";
import {
	deleteOpenCart,
	deleteOpenCarts,
	openCartScopeKey,
	findQueuedSale,
	readOpenCart,
	writeOpenCart,
} from "@/utils/offline/openCart";
import {
	isFreePromoRow,
	scaleRateForUomChange,
	shouldPreserveRateOnUomChange,
} from "@/utils/uomPricingLock";
import { useToast } from "@/composables/useToast";
import { call } from "@/utils/apiWrapper";
import { isPromotionsAppInstalled, promoApi } from "@/utils/promoApi";
import {
	FNF_DISCOUNT_SOURCE,
	FNF_REPLACED_FIELD,
	fnfReplacedDiscount,
	annotateFnfLine,
	clearFnfAnnotations,
	indexFnfLines,
	isFnfAllowedForProfile,
	isFnfLine,
	mergeServerLine,
	fnfEmailBlockMessage,
	isSettingsEligibility,
	normalizeEligibility,
	normalizeFnfResult,
	pickLocalizedMessage,
	stampFnfLine,
	resolveHeaderDiscount,
	stripFnfLine,
} from "@/utils/friendsAndFamily";
import { defineStore } from "pinia";
import { computed, nextTick, ref, toRaw, watch } from "vue";

/**
 * Creates an async task queue that ensures only one operation runs at a time.
 * Subsequent calls while processing will be queued and the latest one executed.
 */
function createAsyncQueue() {
	let isProcessing = false;
	let pendingTask = null;
	let currentAbortController = null;

	return {
		/**
		 * Enqueue a task. If already processing, replaces any pending task.
		 * @param {Function} taskFn - Async function to execute
		 * @returns {Promise} Resolves when task completes or is superseded
		 */
		async enqueue(taskFn) {
			// If currently processing, queue this as the next task (replacing any pending)
			if (isProcessing) {
				pendingTask = taskFn;
				return;
			}

			isProcessing = true;
			currentAbortController = new AbortController();

			try {
				await taskFn(currentAbortController.signal);
			} finally {
				isProcessing = false;
				currentAbortController = null;

				// Process pending task if any
				if (pendingTask) {
					const next = pendingTask;
					pendingTask = null;
					await this.enqueue(next);
				}
			}
		},

		/**
		 * Cancel current operation and clear pending tasks
		 */
		cancel() {
			if (currentAbortController) {
				currentAbortController.abort();
			}
			pendingTask = null;
		},

		/**
		 * Check if queue is currently processing
		 */
		get isProcessing() {
			return isProcessing;
		},

		/**
		 * Check if there's a pending task
		 */
		get hasPending() {
			return pendingTask !== null;
		},
	};
}

// Price modes already warned about offline, so a skipped offer warns once, not every pass.
const warnedOfflineModes = new Set();

/** Warn, once per mode, that an offline offer was skipped for want of its strategy. */
function warnUnhandledOfflineMode(offer) {
	const mode = offer.apply_discount_on_price;
	if (warnedOfflineModes.has(mode)) return;
	warnedOfflineModes.add(mode);
	console.warn(
		`[posCart] offline: no strategy for apply_discount_on_price "${mode}"; ` +
			`offer ${offer.name} is skipped and its lines sell at full price`
	);
}

export const usePOSCartStore = defineStore("posCart", () => {
	// Use the existing invoice composable for core functionality
	const {
		invoiceItems,
		customer,
		subtotal,
		totalTax,
		lineTotalTax,
		totalDiscount,
		grandTotal,
		roundedTotal,
		roundingAdjustment,
		posProfile,
		posOpeningShift,
		payments,
		salesTeam,
		additionalDiscount,
		taxInclusive,
		isSubmitting,
		addItem: addItemToInvoice,
		removeItem,
		updateItemQuantity: baseUpdateItemQuantity,
		submitInvoice: baseSubmitInvoice,
		pendingSubmit,
		setBeforeSubmitRequest,
		hasUnresolvedSubmit: baseHasUnresolvedSubmit,
		pendingMatchesCart: basePendingMatchesCart,
		adoptPendingSubmitFor,
		releaseSubmitKey,
		resolvePendingSubmit: baseResolvePendingSubmit,
		dropPendingSubmit,
		savePaymentDraft,
		paymentDraftName,
		defaultCustomerName,
		clearCart: clearInvoiceCart,
		loadTaxRules,
		setTaxInclusive,
		setDefaultCustomer,
		applyDiscount,
		removeDiscount,
		couponCode,
		applyOffersResource,
		getItemDetailsResource,
		resolveUomPricing,
		recalculateItem,
		rebuildIncrementalCache,
		formatItemsForSubmission,
		payloadRowOwners,
	} = useInvoice();

	const offersStore = usePOSOffersStore();
	const settingsStore = usePOSSettingsStore();

	// Additional cart state
	const pendingItem = ref(null);
	const pendingItemQty = ref(1);
	const appliedOffers = ref([]);
	const appliedCoupon = ref(null);
	const selectionMode = ref("uom"); // 'uom' or 'variant'
	const currentDraftId = ref(null);
	const targetDoctype = ref("Sales Invoice");
	/** POS Settings "Create Only Sales Order": every cart is a Sales Order (D-R3-12). */
	function defaultTargetDoctype() {
		return settingsStore.createOnlySalesOrder ? "Sales Order" : "Sales Invoice";
	}

	// Friends & Family (PN-130). The server decides everything; the cart only
	// mirrors its last answer for badges, breakdowns and cashier messages.
	const fnfEligibility = ref(null); // normalizeEligibility() for the current customer
	const fnfResult = ref(null); // normalizeFnfResult() of the last cart evaluation
	// Set when an order coupon beat F&F (calculate_coupon_discount →
	// suppress_friends_and_family): { code, message, message_en, message_ar }.
	const fnfCouponOverride = ref(null);
	let fnfEligibilityKey = null; // customer the cached eligibility belongs to
	let fnfEligibilityRequest = 0;

	// D-4: the open cart is saved (debounced) for one user, POS Profile and opening
	// shift, and restored after a reload. Saving is off until restoreOpenCart() arms it.
	const OPEN_CART_SAVE_DELAY_MS = 300;
	let openCartScope = null; // { user, pos_profile, pos_opening_shift } while saving
	let openCartSuspended = false; // a cart loaded to edit an offline invoice is not saved
	let openCartTimer = null;
	let stopRepriceWhenOnline = null;
	const cartOfflineId = ref(null); // the offline_id this cart's offline sale is queued under
	// What POSSale's resume re-sends for an unanswered submit (D-19); saved with the cart,
	// so the resume still works after a reload (F6).
	const lastOnlinePayment = ref(null);
	const unverifiedDraftName = ref(null); // a restored payment draft not yet checked on the server
	const alreadySubmittedInvoice = ref(null); // { name, grand_total, ... } of a cart sold before the reload
	const alreadyQueuedSale = ref(null); // { offline_id } of a restored cart already queued offline (F6)

	// Offer processing state management
	const offerProcessingState = ref({
		isProcessing: false, // True while any offer operation is running
		isAutoProcessing: false, // True during automatic offer processing
		lastProcessedAt: 0, // Timestamp of last successful processing
		lastCartHash: "", // Hash of cart state when last processed
		error: null, // Last error if any
		retryCount: 0, // Number of consecutive failures
	});

	// Generation counter to track cart changes and invalidate stale operations
	let cartGeneration = 0;

	// Async queue for sequential offer processing
	const offerQueue = createAsyncQueue();

	// Computed for backward compatibility and UI binding
	const isProcessingOffers = computed(() => offerProcessingState.value.isProcessing);

	/**
	 * Generates a comprehensive hash of the current cart state.
	 * Used to detect ANY change that might affect offer eligibility.
	 */
	/**
	 * Offers-loop guard. Signature of what decides offer eligibility from the
	 * cashier's side (paid lines + customer) — deliberately excludes discounts,
	 * free rows and appliedOffers, which the offer engine itself rewrites.
	 */
	function offerCartSignature() {
		const paid = withCarvedQtyRestored(invoiceItems.value)
			.filter((i) => !i.is_free_item)
			.map((i) => `${i.item_code}:${i.quantity}:${i.uom || ""}:${i.price_list_rate || i.rate || 0}`)
			.join("|");
		return `${paid}::${customer.value?.name || customer.value || "none"}`;
	}

	// offer code -> offerCartSignature() at the moment it was removed as no
	// longer eligible. Auto-apply skips it until the cart really changes, so a
	// removal can never be undone by the very next pass on the same cart.
	const removedOfferSignatures = new Map();

	function rememberRemovedOffers(offers) {
		const sig = offerCartSignature();
		for (const o of offers || []) {
			const code = o?.code || o?.name;
			if (code) removedOfferSignatures.set(code, sig);
		}
	}

	function wasRemovedForCurrentCart(code) {
		const sig = removedOfferSignatures.get(code);
		if (sig === undefined) return false;
		if (sig === offerCartSignature()) return true;
		removedOfferSignatures.delete(code);
		return false;
	}

	function generateCartHash() {
		const items = invoiceItems.value;
		const parts = [
			// Item details: code, quantity, uom, discount
			items
				.map(
					(i) =>
						`${i.item_code}:${i.quantity}:${i.uom || ""}:${i.discount_percentage || 0}`
				)
				.join("|"),
			// Total item count
			items.length.toString(),
			// Subtotal (rounded to avoid floating point issues)
			Math.round((subtotal.value || 0) * 100).toString(),
			// Customer
			customer.value?.name || customer.value || "none",
			// Applied offers count
			appliedOffers.value.length.toString(),
		];
		return parts.join("::");
	}

	// Toast composable
	const { showSuccess, showError, showWarning, showInfo } = useToast();

	// Computed
	const itemCount = computed(() => invoiceItems.value.length);
	const isEmpty = computed(() => invoiceItems.value.length === 0);
	const hasCustomer = computed(() => !!customer.value);

	// Actions
	function addItem(item, qty = 1, _autoAdd = false, currentProfile = null) {
		// An item without a price (no Item Price) cannot be sold at 0; gifts come from offers.
		if (!item.is_free_item && !(Number(item.rate) > 0) && !(Number(item.price_list_rate) > 0)) {
			showError(__("Item {0} has no price and cannot be sold at zero price.", [item.item_code]));
			return;
		}
		if (
			currentProfile &&
			settingsStore.shouldEnforceStockValidation() &&
			shouldValidateItemStock(item)
		) {
			// Only this SKU (paid + free rows of the same item). A free gift of a
			// different product must not inflate requested qty (Iphone 17 x6 +
			// Aqua Water free x1 is 6 phones, not 7).
			const totalQty =
				getCartStockQtyForItem(invoiceItems.value, item.item_code) + rowStockQty(item, qty);
			const warehouse = item.warehouse || currentProfile.warehouse;

			const check = checkStockAvailability(item, totalQty, warehouse);
			if (!check.available) {
				throw new Error(check.error);
			}
		}

		addItemToInvoice(item, qty);
	}

	/**
	 * Update item quantity with stock validation.
	 * Wraps useInvoice.updateItemQuantity to enforce stock limits
	 * when the user clicks +/- or types a new quantity.
	 * The quantity is the paid units. Same-SKU gifts are added ON TOP as a
	 * separate free row (never carved); only legacy carved rows
	 * (gwp_same_item_row === 1, from older drafts) are folded back in here.
	 */
	function updateItemQuantity(itemCode, quantity, uom = null) {
		const item = uom
			? invoiceItems.value.find(
					(i) => i.item_code === itemCode && i.uom === uom && !i.is_free_item
				)
			: invoiceItems.value.find((i) => i.item_code === itemCode && !i.is_free_item);

		if (!item) return;

		const newQty = Number.parseFloat(quantity) || 1;
		// Same-item gift rows carved out of this line
		const carved = invoiceItems.value.filter(
			(i) =>
				i.is_free_item &&
				Number(i.gwp_same_item_row) === 1 &&
				i.item_code === itemCode &&
				i.uom === item.uom
		);
		const lineQty =
			item.quantity + carved.reduce((sum, i) => sum + (Number.parseFloat(i.quantity) || 0), 0);

		// Only validate when quantity is increasing
		if (
			newQty > lineQty &&
			settingsStore.shouldEnforceStockValidation() &&
			shouldValidateItemStock(item)
		) {
			const otherLinesQty =
				getCartStockQtyForItem(invoiceItems.value, item.item_code) - rowStockQty(item, lineQty);
			const totalQty = otherLinesQty + rowStockQty(item, newQty);
			const check = checkStockAvailability(item, totalQty);
			if (!check.available) {
				showWarning(check.error);
				return;
			}
		}

		// Typed qty replaces a legacy carved split; the next offer pass adds the gift on top
		if (carved.length) {
			invoiceItems.value = invoiceItems.value.filter((i) => !carved.includes(i));
		}
		baseUpdateItemQuantity(itemCode, quantity, uom);
	}

	// A cart loaded from a draft leaves its serials held by that draft
	function clearCart({ returnSerials = !currentDraftId.value } = {}) {
		// Cancel any pending offer processing
		debouncedProcessOffers.cancel();
		offerQueue.cancel();

		// The sale is done, held, or abandoned: its saved copy goes too (D-4).
		cancelOpenCartSave();
		stopWaitingForOnline();
		openCartSuspended = false;
		cartOfflineId.value = null;
		lastOnlinePayment.value = null;
		unverifiedDraftName.value = null;

		clearInvoiceCart({ returnSerials });
		// An unanswered submit's key, now marked cleared, stays in the tab's slot so a
		// reload keeps it (Ruling 146 (d)); otherwise the saved cart goes.
		if (openCartScope && !pendingSubmit.value?.unresolved) deleteOpenCart();
		offerHeaderDiscount.value = 0;
		customer.value = null;
		offersStore.clearOneTimeContext();
		appliedOffers.value = [];
		appliedCoupon.value = null;
		fnfEligibility.value = null;
		fnfEligibilityKey = null;
		fnfResult.value = null;
		fnfCouponOverride.value = null;
		currentDraftId.value = null;
		targetDoctype.value = defaultTargetDoctype();

		// Reset offer processing state
		offerProcessingState.value.lastCartHash = "";
		offerProcessingState.value.error = null;
		offerProcessingState.value.retryCount = 0;

		// Sync the empty snapshot
		syncOfferSnapshot();
	}

	function setTargetDoctype(requested) {
		// Only Sales Orders are made while POS Settings say so
		const doctype = settingsStore.createOnlySalesOrder ? "Sales Order" : requested;
		const previous = targetDoctype.value;
		targetDoctype.value = doctype;
		if (doctype === previous) return;
		if (doctype === "Sales Order") {
			// Sales Orders carry no F&F: strip the lines and tell the cashier.
			const hadFnf = invoiceItems.value.some(isFnfLine);
			stripAllFriendsAndFamily();
			fnfResult.value = null;
			if (hadFnf) showInfo(__("Friends & Family discounts apply to invoices only"));
		} else if (previous === "Sales Order") {
			// Back to Sales Invoice: re-run offers so F&F returns.
			fnfEligibilityKey = null;
			refreshFriendsAndFamilyEligibility(true).finally(() => forceRefreshOffers());
		}
	}

	const deliveryDate = ref("");
	const writeOffAmount = ref(0);

	function setDeliveryDate(date) {
		deliveryDate.value = date;
	}

	function setWriteOffAmount(amount) {
		writeOffAmount.value = amount || 0;
	}

	/** The cart on screen, as the doctype it targets (or `doctype`), is the pending submit's cart. */
	function pendingMatchesCart(doctype = targetDoctype.value) {
		return basePendingMatchesCart(doctype);
	}

	/** An unanswered submit of the cart on screen, as the doctype it targets now (F6). */
	function hasUnresolvedSubmit() {
		return baseHasUnresolvedSubmit(targetDoctype.value);
	}

	// The sale a cleared, unanswered submit made: POSSale shows it in a dialog the cashier
	// must dismiss, not a toast that may pass unseen (Ruling 144).
	const madeSaleNotice = ref(null);

	function dismissMadeSaleNotice() {
		madeSaleNotice.value = null;
	}

	/** Back online: settle a cleared submit's key; tell the cashier once about a sale it made (Ruling 143). */
	async function resolvePendingSubmitAndTell() {
		const { made } = await baseResolvePendingSubmit();
		if (made) madeSaleNotice.value = made;
		return made;
	}

	// Ruling 146 (b): "The last sale may already be saved. Is this the same sale?"
	// { identical } while the cashier is asked; decideSubmit() answers it.
	const submitDecision = ref(null);
	let submitDecisionAnswer = null;

	function askIfSameSale(identical) {
		if (submitDecisionAnswer) submitDecisionAnswer(null);
		return new Promise((resolve) => {
			submitDecisionAnswer = resolve;
			submitDecision.value = { identical };
		});
	}

	/** @param {"same"|"new"|null} choice - null: the dialog was closed, nothing is submitted */
	function decideSubmit(choice) {
		const answer = submitDecisionAnswer;
		submitDecisionAnswer = null;
		submitDecision.value = null;
		answer?.(choice === "same" || choice === "new" ? choice : null);
	}

	/**
	 * Before any submit, online or offline, while an earlier submit's outcome is unknown
	 * (Ruling 146): the CASHIER decides, never a silent guess.
	 * (a) Online, the server is asked first. "Made": stop, and tell the cashier (the cart
	 *     stays; the next press is a new sale). "Not made": the key is dropped, go on.
	 * (b) No answer (offline, or the check failed), with this very cart or an edited one:
	 *     "Is this the same sale?" Same: carry the old key, so the server dedups. New: a
	 *     new key. A different cart after Clear Cart is a new sale (Ruling 141).
	 * (c) A Sales Order's key follows the same rules; it keeps its doctype when carried.
	 * @returns {Promise<{stop: true} | {proceed: true, carry: {key: string, doctype: string}|null}>}
	 */
	async function settlePendingSubmit({ offline = offlineState.isOffline } = {}) {
		const pending = pendingSubmit.value;
		if (!pending?.unresolved) return { proceed: true, carry: null };
		// The very cart on screen, unchanged and not cleared (a retry, or the resume after a
		// reload): no gate, the same key (Ruling 149). The server returns the sale it made,
		// waits for one still running, or makes it once; the sale then closes as usual.
		if (!pending.cleared && pendingMatchesCart(targetDoctype.value)) {
			return { proceed: true, carry: { key: pending.key, doctype: pending.doctype || "Sales Invoice" } };
		}
		if (!offline) {
			const { answered, made } = await baseResolvePendingSubmit({ anyKey: true });
			if (made) {
				madeSaleNotice.value = made;
				return { stop: true };
			}
			if (answered) return { proceed: true, carry: null };
		}
		if (pendingSubmit.value !== pending) return { proceed: true, carry: null };
		const identical = pendingMatchesCart(targetDoctype.value);
		if (!identical && pending.cleared) return { proceed: true, carry: null };
		const choice = await askIfSameSale(identical);
		if (!choice) return { stop: true };
		if (pendingSubmit.value !== pending) return { proceed: true, carry: null };
		if (choice === "same") {
			adoptPendingSubmitFor(targetDoctype.value);
			return { proceed: true, carry: { key: pending.key, doctype: pending.doctype || "Sales Invoice" } };
		}
		// A new sale. Online it gets a new key; offline the old key stays, so the
		// reconnect still asks about it once the cart is cleared.
		if (!offline) dropPendingSubmit();
		return { proceed: true, carry: null };
	}

	async function submitInvoice(options = {}) {
		if (invoiceItems.value.length === 0) {
			showWarning(__("Cart is empty"));
			return;
		}
		if (!customer.value) {
			showWarning(__("Please select a customer"));
			return;
		}

		// Capture one-time offer redemptions before submission can clear the cart.
		const customerName = customer.value?.name || customer.value || null;
		const oneTimeRuleNames = appliedOffers.value
			.filter((o) => o.offer?.one_time_per_customer)
			.map((o) => o.code)
			.filter(Boolean);
		const wasOffline = offlineState.isOffline;
		// Online, only the cart the payment-open check priced is submitted (Ruling 110).
		const checked = paymentCheck.value;
		if (!wasOffline && checked && checked.hash !== paymentCheckHash()) {
			paymentCheck.value = null;
			throw new Error(__("The cart changed after its total was checked. Check the total again."));
		}

		// An earlier submit's outcome is unknown: settle it first (Ruling 146). Always, so a
		// stale offline flag can never skip it; offline it asks the cashier, not the server.
		const gate = await settlePendingSubmit({ offline: wasOffline });
		if (gate.stop) return { stopped: true };

		const result = await baseSubmitInvoice(
			targetDoctype.value,
			deliveryDate.value,
			writeOffAmount.value,
			Boolean(options.isCreditSale),
			options.receivableAccount || null
		);
		// Reset write-off amount after successful submission
		if (result) {
			writeOffAmount.value = 0;
			paymentCheck.value = null;
		}
		return result;
	}

	async function createSalesOrder() {
		return await submitInvoice();
	}

	function syncOneTimeContextForCurrentCustomer() {
		const shiftStore = usePOSShiftStore();
		const customerName = customer.value?.name || customer.value || null;
		const defaultCustomer = shiftStore.currentProfile?.customer;
		const isWalkIn = !customerName || customerName === defaultCustomer;

		return offersStore.loadOneTimeContextForCustomer(customerName, { isWalkIn });
	}

	function currentCustomerName() {
		return customer.value?.name || customer.value || null;
	}

	/**
	 * Fetch F&F eligibility for the current customer (PN-125 endpoint).
	 * Cached per customer; pass force=true to re-ask the server. Informational:
	 * pricing is re-checked server-side on every apply / invoice save.
	 */
	/** POS Profile "Allow F&F" — off means no F&F calls, badges or stamps on this profile. */
	function friendsAndFamilyAllowed() {
		// Sales Orders carry no F&F (Phase 3 adds real support).
		if (targetDoctype.value === "Sales Order") return false;
		return isFnfAllowedForProfile(usePOSShiftStore().currentProfile);
	}

	async function refreshFriendsAndFamilyEligibility(force = false) {
		const customerName = currentCustomerName();
		const method = promoApi.checkFriendsAndFamilyEligibility();
		if (!customerName || !method || !friendsAndFamilyAllowed()) {
			fnfEligibility.value = null;
			fnfEligibilityKey = customerName;
			return null;
		}
		// An answer from the F&F Settings (program off…) is asked again: the settings may
		// have changed since (D-R2-03), as a customer change asks again.
		if (!force && fnfEligibilityKey === customerName && !isSettingsEligibility(fnfEligibility.value)) {
			return fnfEligibility.value;
		}
		if (offlineState.isOffline) {
			// Keep the last answer for the same customer; nothing for a new one.
			if (fnfEligibility.value?.customer !== customerName) fnfEligibility.value = null;
			return fnfEligibility.value;
		}

		const requestId = ++fnfEligibilityRequest;
		try {
			const response = await call(method, {
				customer: customerName,
				pos_profile: posProfile.value || undefined,
			});
			if (requestId !== fnfEligibilityRequest || currentCustomerName() !== customerName) {
				return fnfEligibility.value; // customer changed meanwhile
			}
			fnfEligibility.value = normalizeEligibility(response, customerName);
			fnfEligibilityKey = customerName;
		} catch (error) {
			console.error("Error checking Friends & Family eligibility:", error);
			if (requestId === fnfEligibilityRequest) {
				fnfEligibility.value = null;
				fnfEligibilityKey = null; // retry on the next evaluation
			}
		}
		return fnfEligibility.value;
	}

	/** UI language (useLocale() keeps <html lang> in sync; it can't be called inside a store). */
	function currentUiLocale() {
		return globalThis.document?.documentElement?.lang || "en";
	}

	/**
	 * Re-check F&F for the current customer after something server-side changed
	 * (e.g. the email was just OTP-verified) and re-price the cart.
	 */
	async function recheckFriendsAndFamily() {
		const eligibility = await refreshFriendsAndFamilyEligibility(true);
		if (invoiceItems.value.length > 0) triggerOfferProcessing(true);
		return eligibility;
	}

	const PAYMENT_CHECK_MAX_WAIT_MS = 5000;
	// After the payment-open check: the server's total for the cart as it then stood.
	// total: its grand total; payable: what the invoice is paid at (rounded total when rounded).
	const paymentCheck = ref(null); // { total, payable, hash }

	/** The smallest currency unit (currency precision from System Settings). */
	function currencyUnit() {
		return 10 ** -(getPrecision().currency ?? 2);
	}

	function currentPaymentCheck() {
		const checked = paymentCheck.value;
		return checked && checked.hash === paymentCheckHash() ? checked : null;
	}

	/**
	 * What payment collects: the server's payable total of the last payment-open check
	 * while the cart is unchanged since, else the cart's own. Both are the rounded total
	 * when the POS Profile rounds (D-5).
	 */
	const paymentTotal = computed(() => {
		const checked = currentPaymentCheck();
		return checked ? checked.payable : roundedTotal.value;
	});
	/** Rounded minus grand total of what payment collects (0 without rounding). */
	const paymentRoundingAdjustment = computed(() => {
		const checked = currentPaymentCheck();
		return checked ? roundCurrency(checked.payable - checked.total) : roundingAdjustment.value;
	});

	/** The cart as the payment-open check priced it: its lines, header and coupon. */
	function paymentCheckHash() {
		return [generateCartHash(), Number(additionalDiscount.value) || 0, couponCode.value || ""].join("#");
	}

	function lineDiscountPerUnit(item) {
		const qty = Number(item.quantity ?? item.qty) || 1;
		return (Number(item.discount_amount) || 0) / qty;
	}

	/**
	 * Take the checked draft's decisions into the cart (Ruling 110): its F&F lines, the
	 * discounts of its other lines, its free rows, coupon and header discount. Returns
	 * why anything the cart had was dropped, for the cashier.
	 */
	function adoptServerDraft(draft) {
		const unit = currencyUnit();
		const notes = [];
		const fnf = draft.friends_and_family ? normalizeFnfResult(draft.friends_and_family) : null;
		const serverReason = fnf?.bestDiscount ? pickLocalizedMessage(fnf.bestDiscount, currentUiLocale()) : "";

		// The coupon first: while a coupon that replaced F&F is applied (its override),
		// the F&F block below would strip every F&F line (Ruling 112).
		if (appliedCoupon.value && !draft.coupon_code) {
			const code = appliedCoupon.value.code || appliedCoupon.value.name;
			notes.push(serverReason || __("Coupon {0} does not apply to this sale and was removed.", [code]));
			if (isLineLevelCoupon(appliedCoupon.value)) clearCouponLines();
			else removeDiscount();
			couponCode.value = null;
			appliedCoupon.value = null;
			fnfCouponOverride.value = null;
		}

		if (fnf) {
			fnfResult.value = fnf.eligible ? fnf : null;
			// The block's idx is the payload row; a synthesized free row has no cart line.
			const owners = payloadRowOwners(invoiceItems.value);
			const lines = [];
			for (const line of fnf.lines) {
				const owner = owners[Number.parseInt(line?.idx, 10)];
				const index = owner ? invoiceItems.value.indexOf(owner) : -1;
				if (index >= 0) lines.push({ ...line, idx: index });
			}
			applyFriendsAndFamilyOnlyResult({ ...fnf, lines });
		}

		// Other lines, paired in order by item and free flag (the server may drop a gift).
		if (Array.isArray(draft.items)) {
			const serverRows = draft.items;
			let next = 0;
			const dropped = [];
			for (const item of invoiceItems.value) {
				const free = Boolean(item.is_free_item);
				const at = serverRows.findIndex(
					(row, index) =>
						index >= next && row.item_code === item.item_code && Boolean(row.is_free_item) === free
				);
				if (at < 0) {
					if (free) dropped.push(item);
					continue;
				}
				next = at + 1;
				const row = serverRows[at];
				if (free || isFnfLine(item) || isCouponLine(item)) continue;
				const serverPerUnit = Number(row.discount_amount) || 0;
				const qty = Number(item.quantity ?? item.qty) || 1;
				if (row.posnext_discount_source === FNF_DISCOUNT_SOURCE && serverPerUnit > 0) {
					// An F&F row the block did not stamp: its F&F markers come from the row.
					stampFnfLine(item, {
						discount_percentage: Number(row.discount_percentage) || 0,
						discount_amount: serverPerUnit * qty,
						rate: Number(row.rate) || 0,
					});
					recalculateItem(item);
					continue;
				}
				if (Math.abs(serverPerUnit - lineDiscountPerUnit(item)) <= unit) continue;
				if (serverPerUnit <= 0) {
					notes.push(__("The offer on {0} does not apply to this sale and was removed.", [item.item_name || item.item_code]));
					item.discount_percentage = 0;
					item.discount_amount = 0;
					item.discount_source = "";
					item.pricing_rules = [];
					item.is_already_discounted = 0;
				} else {
					// The row's saved rate, not its 2-dp %: priced per unit, the cart then
					// gives the line the draft holds (16.67% of 50 is 41.66, the row 41.67).
					const price = Number(item.price_list_rate || item.rate) || 0;
					const rowRate = Number.parseFloat(row.rate);
					item.discount_percentage =
						price > 0 && Number.isFinite(rowRate) && item.is_rate_manually_edited !== 1
							? ((price - rowRate) / price) * 100
							: Number(row.discount_percentage) || 0;
					item.discount_amount = serverPerUnit * qty;
				}
				recalculateItem(item);
			}
			for (const item of dropped) {
				notes.push(__("The free item {0} does not apply to this sale and was removed.", [item.item_name || item.item_code]));
				const index = invoiceItems.value.indexOf(item);
				if (index >= 0) invoiceItems.value.splice(index, 1);
			}
		}

		// Header discount.
		if ("discount_amount" in draft) {
			const serverHeader = Number(draft.discount_amount) || 0;
			const cartHeader = Number(additionalDiscount.value) || 0;
			if (Math.abs(serverHeader - cartHeader) > unit) {
				if (serverHeader < cartHeader && !notes.length) {
					notes.push(serverReason || __("The invoice discount does not apply in full to this sale."));
				}
				additionalDiscount.value = serverHeader;
			}
		}
		rebuildIncrementalCache();
		return [...new Set(notes.filter(Boolean))];
	}

	/**
	 * Payment-open re-check (Rulings 101, 110): save the cart as an unpaid draft, so
	 * the server re-prices Friends & Family to the customer's remaining allowance, and
	 * take the server draft into the cart; payment collects the server total. Only a
	 * difference above 2 currency units asks the cashier; smaller drift (rounding) is
	 * taken silently.
	 *
	 * Online Sales Invoices only; offline sales and Sales Orders are not checked.
	 * @returns {Promise<{checked: boolean, changed: boolean, previousTotal?: number, total?: number, message?: string}>}
	 */
	/** The draft's rounded total when it rounds (`disable_rounded_total` 0), else its grand total. */
	function draftRounds(draft) {
		return Boolean(draft && "disable_rounded_total" in draft && !Number(draft.disable_rounded_total));
	}

	function draftPayableTotal(draft, grand) {
		const rounds = draftRounds(draft);
		// ERPNext's `rounded_total or grand_total`: a 0.40 that rounds to 0 is paid at 0.40.
		const rounded = Number.parseFloat(draft?.rounded_total);
		return rounds && rounded ? rounded : grand;
	}

	async function checkPriceBeforePayment() {
		if (offlineState.isOffline || targetDoctype.value !== "Sales Invoice") {
			return { checked: false, changed: false };
		}
		// The cart's own offer evaluation first, so the total compared is the one shown.
		const waitUntil = Date.now() + PAYMENT_CHECK_MAX_WAIT_MS;
		while (offerProcessingState.value.isProcessing && Date.now() < waitUntil) {
			await new Promise((resolve) => setTimeout(resolve, 100));
		}

		// A restored draft is checked first: a sold cart is never priced or paid again (Ruling 136).
		const gate = await ensurePaymentAllowed();
		if (gate.alreadySubmitted) return { checked: false, changed: false, alreadySubmitted: true };
		if (!gate.allowed) throw new Error(gate.message);

		const previousGrand = Number(grandTotal.value) || 0;
		const previousPayable = Number(roundedTotal.value) || 0;
		paymentCheck.value = null;
		let draft;
		try {
			draft = await savePaymentDraft();
		} catch (error) {
			// The draft is a submitted invoice (Ruling 136 (c)): read it and close the cart.
			if (!error?.already_submitted) throw error;
			unverifiedDraftName.value = error.invoice_name;
			if ((await verifyPaymentDraft()) === "submitted") {
				return { checked: false, changed: false, alreadySubmitted: true };
			}
			throw error;
		}
		const total = Number.parseFloat(draft.grand_total) || 0;
		const payable = draftPayableTotal(draft, total);
		const notes = adoptServerDraft(draft);
		paymentCheck.value = { total, payable, hash: paymentCheckHash() };
		// Ruling 134: ask when what is collected changes and either total drifts by more than
		// two currency units. A cent of drift stays silent (USD rounds to 0.01, Ruling 110 I4);
		// a rounding step does not (EGP 287 → 288, CHF 10.00 → 10.05). The cashier is shown
		// what is collected.
		const tolerance = 2 * currencyUnit() + 1e-9;
		const changed =
			Math.abs(payable - previousPayable) > 1e-9 &&
			(Math.abs(total - previousGrand) > tolerance || Math.abs(payable - previousPayable) > tolerance);
		const message = notes.join(" ");
		if (!changed && message) showWarning(message);
		return { checked: true, changed, previousTotal: previousPayable, total: payable, message };
	}

	/**
	 * D-16 (D-R2-11): a line coupon is never carried to another customer. Its lines go
	 * back to what they had before it, minus the old customer's F&F, and are re-priced.
	 */
	function dropLineCouponForCustomerChange() {
		const coupon = appliedCoupon.value;
		if (!isLineLevelCoupon(coupon)) return;
		for (const item of invoiceItems.value) stripStashedFnf(item);
		clearCouponLines();
		couponCode.value = null;
		appliedCoupon.value = null;
		fnfCouponOverride.value = null;
		showWarning(__("Coupon {0} removed: the customer changed", [coupon.code || coupon.name || ""]));
		forceRefreshOffers();
	}

	/**
	 * @param {Object|string|null} selectedCustomer
	 * @param {{ restoring?: boolean }} options restoring: a loaded draft sets its own
	 *   customer; its coupon is restored after, so nothing is dropped here.
	 */
	async function setCustomer(selectedCustomer, { restoring = false } = {}) {
		const previous = currentCustomerName();
		const wasEligible = Boolean(fnfEligibility.value?.eligible);
		customer.value = selectedCustomer;
		if (!restoring && currentCustomerName() !== previous) dropLineCouponForCustomerChange();
		const [, eligibility] = await Promise.all([
			syncOneTimeContextForCurrentCustomer(),
			refreshFriendsAndFamilyEligibility(true),
		]);
		// The same customer, saved again (e.g. a new email clears its verification): when
		// its F&F eligibility changed, re-price the open cart as a customer change does (D-R3-07).
		if (
			!restoring &&
			currentCustomerName() === previous &&
			Boolean(eligibility?.eligible) !== wasEligible &&
			invoiceItems.value.length > 0
		) {
			triggerOfferProcessing(true);
		}
		const emailBlock = fnfEmailBlockMessage(eligibility);
		if (emailBlock && currentCustomerName() !== previous) {
			showWarning(emailBlock);
		}
		if (eligibility?.eligible && currentCustomerName() !== previous) {
			showSuccess(
				pickLocalizedMessage(eligibility.customerMessage, currentUiLocale()) ||
					__("Friends & Family customer — {0}% discount", [
						String(eligibility.discountPercentage),
					])
			);
		}
	}

	async function loadDefaultCustomer() {
		const shiftStore = usePOSShiftStore();
		const profileCustomer =
			shiftStore.currentProfile?.customer || shiftStore.profileCustomer || null;
		await setDefaultCustomer(profileCustomer);
		await Promise.all([
			syncOneTimeContextForCurrentCustomer(),
			refreshFriendsAndFamilyEligibility(true),
		]);
	}

	function setPendingItem(item, qty = 1, mode = "uom") {
		pendingItem.value = item;
		pendingItemQty.value = qty;
		selectionMode.value = mode;
	}

	function clearPendingItem() {
		pendingItem.value = null;
		pendingItemQty.value = 1;
		selectionMode.value = "uom";
	}

	// Discount & Offer Management
	// An order discount and a whole-cart coupon share the header, so only one applies at a time
	const offerHeaderDiscount = ref(0);

	function isWholeCartCoupon(coupon) {
		return Boolean(coupon) && !isLineLevelCoupon(coupon);
	}

	function applyDiscountToCart(discount) {
		// PN-128/130: an order coupon that beat Friends & Family replaces it —
		// drop the F&F line stamps so the two are never combined in the cart.
		if (discount?.suppress_friends_and_family) {
			fnfCouponOverride.value = {
				code: discount.code || discount.name || "",
				message: discount.fnf_message?.message || "",
				message_en: discount.fnf_message?.message_en || "",
				message_ar: discount.fnf_message?.message_ar || "",
			};
			stripAllFriendsAndFamily();
		} else {
			fnfCouponOverride.value = null;
		}
		if (isLineLevelCoupon(discount)) {
			if (appliedCoupon.value && !isLineLevelCoupon(appliedCoupon.value)) {
				removeDiscount();
			}
			const amount = applyCouponLineUpdates(discount.code, discount.line_updates, discount.coupon);
			couponCode.value = discount.code;
			appliedCoupon.value = { ...discount, amount };
			showSuccess(__("{0} applied successfully", [discount.name]));
			return;
		}
		if (offerHeaderDiscount.value > 0) {
			showWarning(__("{0} can't be combined with the order discount already applied", [discount.name]));
			return false;
		}
		clearCouponLines();
		applyDiscount(discount);
		appliedCoupon.value = discount;
		showSuccess(__("{0} applied successfully", [discount.name]));
	}

	function removeDiscountFromCart() {
		const hadFnfOverride = Boolean(fnfCouponOverride.value);
		appliedOffers.value = [];
		if (isLineLevelCoupon(appliedCoupon.value)) {
			clearCouponLines();
			couponCode.value = null;
		} else {
			removeDiscount();
		}
		appliedCoupon.value = null;
		fnfCouponOverride.value = null;
		showSuccess(__("Discount has been removed from cart"));
		// Bring Friends & Family back now that the coupon is gone.
		if (hadFnfOverride) forceRefreshOffers();
	}

	/**
	 * The server refused the cart's coupon at Checkout (Coupon Not Applicable, e.g. used
	 * up by another cashier since it was applied, D-R3-08): drop it and re-price.
	 * Returns whether a coupon was dropped.
	 */
	function dropRefusedCoupon() {
		const coupon = appliedCoupon.value;
		if (!coupon && !couponCode.value) return false;
		if (isLineLevelCoupon(coupon)) {
			clearCouponLines();
			couponCode.value = null;
		} else {
			removeDiscount();
		}
		appliedCoupon.value = null;
		fnfCouponOverride.value = null;
		forceRefreshOffers();
		return true;
	}

	/** Drop every F&F stamp in the cart (coupon won, program ended, customer changed…). */
	function stripStashedFnf(item) {
		if (isCouponLine(item) && item.pre_coupon_discount?.discount_source === FNF_DISCOUNT_SOURCE) {
			item.pre_coupon_discount = { discount_percentage: 0, discount_amount: 0, discount_source: "", is_already_discounted: 0 };
			item[FNF_REPLACED_FIELD] = null;
			return true;
		}
		return false;
	}

	function stripAllFriendsAndFamily({ keepAnnotations = false } = {}) {
		let changed = false;
		for (const item of invoiceItems.value) {
			// A coupon line keeps its F&F in the stash; removing the coupon must not bring it back
			stripStashedFnf(item);
			if (stripFnfLine(item)) {
				changed = true;
				recalculateItem(item);
			}
			if (!keepAnnotations) clearFnfAnnotations(item);
		}
		if (changed) rebuildIncrementalCache();
		return changed;
	}

	/**
	 * Mirror an F&F-only evaluation (apply_friends_and_family_discount) onto
	 * the cart: stamp lines F&F wins, strip stale stamps elsewhere.
	 */
	function applyFriendsAndFamilyOnlyResult(result) {
		const lines = indexFnfLines(result);
		invoiceItems.value.forEach((item, index) => {
			// A coupon line is the coupon's: its F&F is kept in pre_coupon_discount and comes back with it
			if (isCouponLine(item)) return;
			const line = lines.get(index);
			if (line?.applies && !fnfCouponOverride.value) {
				stampFnfLine(item, line);
			} else {
				stripFnfLine(item);
				annotateFnfLine(item, line || null);
			}
			recalculateItem(item);
		});
		rebuildIncrementalCache();
	}

	/**
	 * No promotion needed a server round-trip, but F&F may still apply (or a
	 * stale F&F stamp must be removed). Uses the dedicated F&F endpoint so the
	 * cart shows the discount before the invoice is saved.
	 */
	async function evaluateFriendsAndFamilyOnly(currentProfile, signal = null, generation = 0) {
		const hasFnfLines = invoiceItems.value.some(isFnfLine);
		const eligible = Boolean(fnfEligibility.value?.eligible);
		if (fnfEligibility.value && !eligible) invoiceItems.value.forEach(stripStashedFnf);
		const method = promoApi.applyFriendsAndFamilyDiscount();

		if (!method || invoiceItems.value.length === 0 || !friendsAndFamilyAllowed()) {
			stripAllFriendsAndFamily();
			fnfResult.value = null;
			return;
		}
		if (fnfCouponOverride.value) {
			stripAllFriendsAndFamily();
			fnfResult.value = null;
			return;
		}
		if (!eligible && !hasFnfLines && fnfEligibility.value) {
			// Known-ineligible customer and nothing to clean up.
			if (fnfResult.value) {
				fnfResult.value = null;
				for (const item of invoiceItems.value) clearFnfAnnotations(item);
			}
			return;
		}
		if (!eligible && !hasFnfLines) return;

		const payload = buildOfferEvaluationPayload(currentProfile);
		const response = await call(method, {
			customer: payload.customer,
			items: payload.items,
			mutate: 1,
			pos_profile: posProfile.value || undefined,
		});
		if (signal?.aborted || (generation > 0 && generation < cartGeneration)) return;

		const result = normalizeFnfResult(response);
		fnfResult.value = result?.eligible ? result : null;
		applyFriendsAndFamilyOnlyResult(result);
	}

	// Line-level coupons (priced by posnext_promotions) discount only their eligible lines.
	// Those lines are tagged so the server can re-check them on submit.
	const COUPON_REVALIDATE_MAX_WAIT_MS = 5000;
	let couponRevalidateTimer = null;
	let couponRevalidateSeq = 0;

	function isLineLevelCoupon(coupon) {
		return Boolean(coupon?.line_level);
	}

	// The coupon is always priced against the lines as they are without it.
	function buildCouponItemsPayload() {
		return toRaw(invoiceItems.value).map((item) => {
			const pre = preCouponDiscount(item);
			return {
				item_code: item.item_code,
				item_group: item.item_group,
				brand: item.brand,
				qty: item.quantity,
				uom: item.uom,
				// At currency precision, as the invoice row sends it (a UOM change leaves 10/3)
				price_list_rate: roundCurrency(item.price_list_rate || item.rate),
				rate: item.rate,
				amount: item.amount,
				discount_percentage: pre.discount_percentage || 0,
				discount_amount: pre.discount_amount || 0,
				pricing_rules: normalizePricingRules(item.pricing_rules).join(","),
				is_free_item: item.is_free_item || 0,
				is_already_discounted: pre.is_already_discounted || 0,
				discount_source: pre.discount_source || "",
				coupon_code: "",
				...fnfReplacedDiscount(item, pre.discount_source),
			};
		});
	}

	function dropCouponFromLine(item) {
		restorePreCouponDiscount(item);
		item.coupon_code = null;
		item.coupon_fixed_discount = null;
		item.coupon_percentage_cap = null;
		item.coupon_stacked = false;
		recalculateItem(item);
	}

	function clearCouponLines() {
		let changed = false;
		for (const item of invoiceItems.value) {
			if (item.discount_source !== COUPON_DISCOUNT_SOURCE) continue;
			dropCouponFromLine(item);
			changed = true;
		}
		if (changed) rebuildIncrementalCache();
	}

	/**
	 * Apply server line_updates (from validate_coupon) to the cart.
	 * line_key is the 0-based index of the line in the items payload.
	 * @returns {number} total coupon discount now on the cart
	 */
	function applyCouponLineUpdates(code, lineUpdates, coupon) {
		clearCouponLines();
		const couponPercentage =
			coupon?.discount_type === "Percentage" ? Number(coupon.discount_percentage) || 0 : 0;
		let total = 0;
		for (const update of lineUpdates || []) {
			const item = invoiceItems.value[update.line_key];
			// Cart changed while the request was in flight; the revalidation watcher catches up.
			if (!item || item.item_code !== update.item_code) continue;
			const percentage = Number.parseFloat(update.discount_percentage) || 0;
			const fixedAmount = percentage > 0 ? 0 : Number.parseFloat(update.discount_amount) || 0;
			// A stacked line's discount includes what it already had, so the coupon % is no cap for it.
			const stacked = Boolean(update.stacked);
			stashPreCouponDiscount(item);
			item.discount_percentage = percentage;
			item.discount_amount = fixedAmount;
			item.coupon_fixed_discount = percentage > 0 ? null : fixedAmount;
			item.coupon_percentage_cap = percentage > 0 || stacked ? null : couponPercentage || null;
			// Only a stacked line keeps what it had under the coupon; the cart label says so (D-R2-05).
			item.coupon_stacked = stacked;
			item.discount_source = COUPON_DISCOUNT_SOURCE;
			item.coupon_code = code;
			recalculateItem(item);
			// The server names the coupon's own share coupon_only_discount (older builds: coupon_discount_amount)
			const couponPart = Number.parseFloat(update.coupon_only_discount ?? update.coupon_discount_amount);
			total += Number.isFinite(couponPart) ? couponPart : item.discount_amount;
		}
		rebuildIncrementalCache();
		return total;
	}

	// Keep fixed coupon lines within their allocation after a local quantity/UOM change.
	function capFixedCouponLines() {
		const { currency } = getPrecision();
		let changed = false;
		for (const item of invoiceItems.value) {
			if (!hasFixedCouponDiscount(item)) continue;
			const allowed = fixedCouponLineDiscount(item, currency);
			if (Math.abs((item.discount_amount || 0) - allowed) < 1e-9) continue;
			item.discount_percentage = 0;
			item.discount_amount = allowed;
			recalculateItem(item);
			changed = true;
		}
		if (changed) rebuildIncrementalCache();
	}

	/**
	 * Re-attach a scoped coupon saved with a held cart, or drop its line discounts
	 * when the coupon itself was not saved (they must never outlive the coupon).
	 */
	function restoreLineCoupon(coupon) {
		const code = coupon?.code;
		const hasLines = Boolean(code) && invoiceItems.value.some((item) => isCouponLine(item) && item.coupon_code === code);
		if (isLineLevelCoupon(coupon) && hasLines) {
			for (const item of invoiceItems.value) {
				if (isCouponLine(item) && item.coupon_code !== code) {
					dropCouponFromLine(item);
				}
			}
			appliedCoupon.value = coupon;
			couponCode.value = code;
			capFixedCouponLines();
			rebuildIncrementalCache();
			scheduleCouponRevalidation();
			return;
		}
		clearCouponLines();
		if (isLineLevelCoupon(appliedCoupon.value)) {
			appliedCoupon.value = null;
			couponCode.value = null;
		}
	}

	function scheduleCouponRevalidation() {
		if (couponRevalidateTimer) clearTimeout(couponRevalidateTimer);
		couponRevalidateTimer = setTimeout(() => {
			couponRevalidateTimer = null;
			revalidateLineCoupon();
		}, 400);
	}

	async function revalidateLineCoupon() {
		const coupon = appliedCoupon.value;
		// Offline carts keep their tagged lines; the server re-checks them when the invoice syncs.
		if (!isLineLevelCoupon(coupon) || offlineState.isOffline) return;

		const seq = ++couponRevalidateSeq;
		const waitUntil = Date.now() + COUPON_REVALIDATE_MAX_WAIT_MS;
		while (offerProcessingState.value.isProcessing && Date.now() < waitUntil) {
			await new Promise((resolve) => setTimeout(resolve, 100));
			if (seq !== couponRevalidateSeq) return;
		}

		try {
			const result = await call(promoApi.validateCoupon(), {
				coupon_code: coupon.code,
				customer: customer.value?.name || customer.value,
				company: usePOSShiftStore().currentProfile?.company,
				pos_profile: posProfile.value || undefined,
				items: JSON.stringify(buildCouponItemsPayload()),
				target_doctype: targetDoctype.value,
			});
			if (seq !== couponRevalidateSeq || appliedCoupon.value?.code !== coupon.code) return;

			if (!result?.valid) {
				clearCouponLines();
				couponCode.value = null;
				appliedCoupon.value = null;
				showWarning(
					__("Coupon {0} removed: {1}", [
						coupon.code,
						result?.message || __("Cart no longer meets requirements"),
					])
				);
				return;
			}

			const amount = applyCouponLineUpdates(coupon.code, result.line_updates, coupon.coupon);
			appliedCoupon.value = { ...appliedCoupon.value, amount, line_updates: result.line_updates };
		} catch (error) {
			console.error("Error re-validating coupon:", error);
			showWarning(
				__("Could not re-check coupon {0}. It will be validated again on payment.", [
					coupon.code,
				])
			);
		}
	}

	function buildOfferEvaluationPayload(currentProfile) {
		// Use toRaw() to ensure we get current, non-reactive values (prevents stale cached quantities)
		// Carved same-SKU free units count as paid demand (see withCarvedQtyRestored)
		const rawItems = withCarvedQtyRestored(toRaw(invoiceItems.value));

		return {
			// The cart's own target: one-time offers apply to invoices only.
			doctype: targetDoctype.value || "Sales Invoice",
			pos_profile: posProfile.value,
			customer: customer.value?.name || customer.value || currentProfile?.customer,
			company: currentProfile?.company,
			selling_price_list: currentProfile?.selling_price_list,
			currency: currentProfile?.currency,
			// A whole-cart coupon's amount is not sent, so the server can't echo it back as an order discount
			discount_amount: isWholeCartCoupon(appliedCoupon.value) ? 0 : additionalDiscount.value || 0,
			coupon_code: appliedCoupon.value?.name || "",
			// Offers see coupon lines without the coupon; otherwise its discount reads as a manual one.
			items: rawItems.map((item) => {
				const pre = preCouponDiscount(item);
				return {
					item_code: item.item_code,
					item_name: item.item_name,
					qty: item.quantity,
					rate: item.rate,
					uom: item.uom,
					warehouse: item.warehouse,
					conversion_factor: item.conversion_factor || 1,
					// At currency precision, as the invoice row sends it (a UOM change leaves 10/3)
					price_list_rate: roundCurrency(item.price_list_rate || item.rate),
					discount_percentage: pre.discount_percentage || 0,
					discount_amount: pre.discount_amount || 0,
					pricing_rules: item.pricing_rules || "",
					is_already_discounted: pre.is_already_discounted || 0,
					discount_source: pre.discount_source || "",
					coupon_code: "",
					...fnfReplacedDiscount(item, pre.discount_source),
					item_group: item.item_group,
					brand: item.brand,
					amount: item.amount,
					is_free_item: item.is_free_item || 0,
				};
			}),
		};
	}

	/** @returns {boolean} true when the line is a coupon line (handled here, its coupon kept) */
	function dropPromotionUnderCoupon(item) {
		if (!isCouponLine(item)) return false;
		if (hasPricingRules(item.pricing_rules)) {
			item.pricing_rules = [];
			item.is_accumulative_discount = 0;
			updatePreCouponDiscount(item, {
				discount_percentage: 0,
				discount_amount: 0,
				discount_source: "",
				is_already_discounted: 0,
			});
		}
		return true;
	}

	/**
	 * Offers changed the discount under a coupon line: keep the coupon on it and
	 * re-price the coupon against the line's new pre-coupon discount.
	 */
	function updatePreCouponDiscount(item, next) {
		const pre = preCouponDiscount(item);
		const changed =
			Number(pre.discount_percentage || 0) !== Number(next.discount_percentage || 0) ||
			(next.discount_percentage > 0
				? false
				: Number(pre.discount_amount || 0) !== Number(next.discount_amount || 0)) ||
			(pre.discount_source || "") !== (next.discount_source || "") ||
			Number(pre.is_already_discounted || 0) !== Number(next.is_already_discounted || 0);
		item.pre_coupon_discount = { ...next };
		if (changed) scheduleCouponRevalidation();
	}

	/**
	 * Check if pricing_rules has a value (handles string or array).
	 */
	function hasPricingRules(value) {
		if (!value) return false;
		if (Array.isArray(value)) return value.length > 0;
		return typeof value === "string" && value.trim().length > 0;
	}

	/**
	 * Normalize pricing_rules to an array. The server echoes it back as a
	 * comma-separated string (see useInvoice.js#stringifyPricingRules) —
	 * spreading a string directly (`[...str]`) splits it into individual
	 * characters instead of rule names, corrupting the field for offline
	 * stacking / merge logic below.
	 */
	function normalizePricingRules(value) {
		if (Array.isArray(value)) return [...value];
		if (typeof value === "string" && value.trim()) {
			return value
				.split(",")
				.map((s) => s.trim())
				.filter(Boolean);
		}
		return [];
	}

	/**
	 * Sync discounts from server response to cart items.
	 * Server returns items in same order as sent (handles duplicate SKUs).
	 */
	function applyDiscountsFromServer(serverItems, friendsAndFamily = null) {
		if (!Array.isArray(serverItems)) return false;

		let hasDiscounts = false;
		// F&F stamps are trusted only when the response's F&F block says the
		// line applies. Without a block (ineligible customer) the server echoes
		// the request lines back — an old F&F % must not survive as "manual".
		const fnfLines = indexFnfLines(friendsAndFamily);
		const fnfSuppressed =
			Boolean(fnfCouponOverride.value) || targetDoctype.value === "Sales Order";
		fnfResult.value = friendsAndFamily?.eligible && !fnfSuppressed ? friendsAndFamily : null;

		invoiceItems.value.forEach((item, index) => {
			const serverItem = serverItems[index] || {};
			const discountPct = Number.parseFloat(serverItem.discount_percentage) || 0;
			const discountAmt = Number.parseFloat(serverItem.discount_amount) || 0;
			const serverDiscounted =
				hasPricingRules(serverItem.pricing_rules) || discountPct > 0 || discountAmt > 0;

			if (isCouponLine(item)) {
				if (serverDiscounted) {
					updatePreCouponDiscount(item, {
						discount_percentage: discountPct,
						discount_amount: discountAmt,
						discount_source: serverItem.discount_source || "",
						is_already_discounted: serverItem.is_already_discounted ? 1 : 0,
					});
				} else if (hasPricingRules(item.pricing_rules)) {
					// The promotion under the coupon no longer applies.
					updatePreCouponDiscount(item, {
						discount_percentage: 0,
						discount_amount: 0,
						discount_source: "",
						is_already_discounted: 0,
					});
				}
				item.pricing_rules = normalizePricingRules(serverItem.pricing_rules);
				// The snapshot F&F signed for the line under the coupon, if F&F holds it.
				const fnfLine = fnfLines.get(index);
				item[FNF_REPLACED_FIELD] = fnfLine?.applies ? fnfLine[FNF_REPLACED_FIELD] || null : null;
				item.free_qty = Number.parseFloat(serverItem.free_qty) || 0;
				item.is_accumulative_discount =
					serverItem.discount_source === "accumulative_promotion" ? 1 : 0;
				return;
			}

			const { discounted } = mergeServerLine(item, serverItems[index] || {}, fnfLines.get(index), {
				fnfSuppressed,
			});
			if (discounted) hasDiscounts = true;
			recalculateItem(item);
		});

		rebuildIncrementalCache();
		return hasDiscounts;
	}

	/**
	 * Processes free items from backend offer response.
	 *
	 * ERPNext represents product discounts as separate SI rows: paid line(s) plus
	 * one or more rows with is_free_item=1 (see pricing_rule tests for same_item).
	 * We always add a dedicated free row so formatItemsForSubmission sends qty > 0
	 * for stock and accounting; annotating only free_qty on the paid line never
	 * reaches Sales Invoice Item (there is no free_qty field server-side).
	 *
	 * @param {Array} freeItems - Array of free items from backend (e.g., [{item_code, qty, uom, item_name}])
	 * @returns {void}
	 */
	function processFreeItems(freeItems) {
		// Restore qty previously carved into same-SKU free rows, then rebuild.
		// See syncCartFreeItems — gwp_same_item_row is client-only; skipping this
		// undercharges scanned units.
		// Same-SKU gifts are added on top of paid qty (never carved); min_qty kept for reference
		const withMinQty = (freeItems || []).map((free) => ({
			...free,
			min_qty:
				free.min_qty ??
				resolveFreeItemMinQty(free, offersStore.availableOffers, appliedOffers.value),
		}));
		invoiceItems.value = syncCartFreeItems(invoiceItems.value, withMinQty, {
			recalculateItem,
		});
		rebuildIncrementalCache();
	}

	/**
	 * Extracts and normalizes the offer response from backend
	 *
	 * @param {Object} response - Raw API response from backend
	 * @returns {Object} Normalized response with items, freeItems, appliedRules,
	 *                   and headerDiscount (transaction-scope discount).
	 *
	 * IMPORTANT: No fallback for appliedRules - we trust the backend's response.
	 * If backend returns empty applied_pricing_rules, it means NO offers were applied.
	 * Previously we had a fallback that caused false "applied" status.
	 */
	function parseOfferResponse(response) {
		const payload = response?.message || response || {};

		return {
			items: Array.isArray(payload.items) ? payload.items : [],
			freeItems: Array.isArray(payload.free_items) ? payload.free_items : [],
			// CRITICAL: Only trust explicitly returned rules - NO FALLBACK
			// If backend doesn't return applied_pricing_rules, NO offers were applied
			appliedRules: Array.isArray(payload.applied_pricing_rules)
				? payload.applied_pricing_rules
				: [],
			// Header-level (transaction-scope) discount surfaced by the server when an
			// apply_on=Transaction Price rule fires. discountAmount is the resolved
			// SAR amount (already computed from % if the rule is percentage-based).
			// Zero/empty when no such rule applies.
			headerDiscount: {
				discountAmount: Number.parseFloat(payload.discount_amount) || 0,
				applyDiscountOn: payload.apply_discount_on || null,
			},
			// PN-130: F&F decision + best-discount explanation. null when the
			// server sent no F&F block (ineligible customer / program off).
			friendsAndFamily: normalizeFnfResult(payload.friends_and_family, payload.best_discount),
		};
	}

	/**
	 * Apply (or clear) the header-level discount the server surfaced when an
	 * apply_on=Transaction Price rule fired. ERPNext stores this on the invoice
	 * header as discount_amount + apply_discount_on; in the cart we mirror it
	 * via additionalDiscount.value (which is sent back as discount_amount in
	 * the invoice payload — see useInvoice.js#submitInvoice).
	 *
	 * Pass an empty/zero headerDiscount to clear (e.g. when no transaction-level
	 * rule applies on the current cart). A whole-cart coupon keeps the header
	 * while no order discount applies, and is removed, with a warning, when one does.
	 */
	function applyHeaderDiscountFromServer(headerDiscount) {
		const { amount, keepCoupon } = resolveHeaderDiscount(
			headerDiscount?.discountAmount,
			isWholeCartCoupon(appliedCoupon.value) ? appliedCoupon.value : null
		);
		offerHeaderDiscount.value = amount;
		const coupon = appliedCoupon.value;
		if (isWholeCartCoupon(coupon)) {
			if (keepCoupon) {
				// The applied POS Coupon owns the header discount — the server
				// reported no transaction-rule discount, which must not wipe it.
				applyDiscount(coupon);
				return;
			}
			removeDiscount();
			appliedCoupon.value = null;
			fnfCouponOverride.value = null;
			showWarning(__("Coupon {0} removed: it can't be combined with the order discount", [coupon.code]));
		}
		additionalDiscount.value = offerHeaderDiscount.value;
		rebuildIncrementalCache();
	}

	function getAppliedOfferCodes() {
		return appliedOffers.value.map((entry) => entry.code);
	}

	function filterActiveOffers(appliedRuleNames = []) {
		if (!Array.isArray(appliedRuleNames) || appliedRuleNames.length === 0) {
			appliedOffers.value = [];
			return;
		}

		appliedOffers.value = appliedOffers.value.filter((entry) =>
			appliedRuleNames.includes(entry.code)
		);
	}

	async function applyOffer(offer, currentProfile, offersDialogRef = null) {
		if (!offer) {
			console.error("No offer provided");
			offersDialogRef?.resetApplyingState();
			return false;
		}

		const offerCode = offer.name;
		const existingCodes = getAppliedOfferCodes();
		const alreadyApplied = existingCodes.includes(offerCode);

		if (alreadyApplied) {
			return await removeOffer(offerCode, currentProfile, offersDialogRef);
		}

		if (!posProfile.value || invoiceItems.value.length === 0) {
			showWarning(__("Add items to the cart before applying an offer."));
			offersDialogRef?.resetApplyingState();
			return false;
		}

		// Cancel any pending auto-processing since user is manually applying
		debouncedProcessOffers.cancel();
		offerQueue.cancel();

		let result = false;

		await offerQueue.enqueue(async (signal) => {
			// Check if operation was cancelled
			if (signal?.aborted) return;

			try {
				offerProcessingState.value.isProcessing = true;
				offerProcessingState.value.error = null;

				const invoiceData = buildOfferEvaluationPayload(currentProfile);
				const pricedLines = snapshotPricedLines();
				const sentHash = generateCartHash();
				const offerNames = [...new Set([...existingCodes, offerCode])];

				const response = await applyOffersResource.submit({
					invoice_data: invoiceData,
					selected_offers: offerNames,
				});

				// Check if cancelled during API call
				if (signal?.aborted) return;

				// The cart changed while the request was in flight: the answer prices a cart
				// that is gone, so it is dropped, as the auto pass drops a stale answer (I-1r).
				if (generateCartHash() !== sentHash) {
					showWarning(__("The cart changed while the offer was being applied. Please apply it again."));
					offersDialogRef?.resetApplyingState();
					result = false;
					return;
				}

				const {
					items: responseItems,
					freeItems,
					appliedRules,
					headerDiscount,
					friendsAndFamily,
				} = parseOfferResponse(response);

				applyDiscountsFromServer(responseItems, friendsAndFamily);
				processFreeItems(freeItems);
				applyHeaderDiscountFromServer(headerDiscount);
				filterActiveOffers(appliedRules);

				const offerApplied = appliedRules.includes(offerCode);

				if (!offerApplied) {
					// No new offer applied - restore previous state without new offer
					if (existingCodes.length) {
						try {
							const rollbackResponse = await applyOffersResource.submit({
								invoice_data: invoiceData,
								selected_offers: existingCodes,
							});
							const {
								items: rollbackItems,
								freeItems: rollbackFreeItems,
								appliedRules: rollbackRules,
								headerDiscount: rollbackHeaderDiscount,
								friendsAndFamily: rollbackFriendsAndFamily,
							} = parseOfferResponse(rollbackResponse);

							applyDiscountsFromServer(rollbackItems, rollbackFriendsAndFamily);
							processFreeItems(rollbackFreeItems);
							applyHeaderDiscountFromServer(rollbackHeaderDiscount);
							filterActiveOffers(rollbackRules);
						} catch (rollbackError) {
							console.error("Error rolling back offers:", rollbackError);
						}
					}

					showWarning(__("Your cart doesn't meet the requirements for this offer."));
					offersDialogRef?.resetApplyingState();
					result = false;
					return;
				}

				const offerRuleCodes = appliedRules.includes(offerCode)
					? appliedRules.filter((ruleName) => ruleName === offerCode)
					: [offerCode];

				const updatedEntries = appliedOffers.value.filter(
					(entry) => entry.code !== offerCode
				);
				updatedEntries.push({
					name: offer.title || offer.name,
					code: offerCode,
					offer, // Store full offer object for validation
					source: "manual",
					applied: true,
					rules: offerRuleCodes,
					// Store constraints for quick validation
					min_qty: offer.min_qty,
					max_qty: offer.max_qty,
					min_amt: offer.min_amt,
					max_amt: offer.max_amt,
				});
				appliedOffers.value = updatedEntries;
				stampServerScopes(pricedLines);

				offerProcessingState.value.lastProcessedAt = Date.now();

				// Wait for Vue reactivity to propagate before showing toast
				await nextTick();

				showSuccess(__("{0} applied successfully", [offer.title || offer.name]));
				result = true;
			} catch (error) {
				if (signal?.aborted) return;
				console.error("Error applying offer:", error);
				offerProcessingState.value.error = error.message;
				showError(__("Failed to apply offer. Please try again."));
				offersDialogRef?.resetApplyingState();
				result = false;
			} finally {
				offerProcessingState.value.isProcessing = false;
			}
		});

		return result;
	}

	/**
	 * No offer is applied any more: drop every line's promotion discount and its rules.
	 * A rule left on a line would still block F&F in the F&F-only check (Task 8q).
	 */
	function dropOfferDiscountsFromLines() {
		invoiceItems.value.forEach((item) => {
			if (dropPromotionUnderCoupon(item)) return;
			// Drop the rule itself, not only its discount: a Buy X Get Y line keeps
			// pricing_rules after qty falls under min_qty, and the F&F pass would
			// then see a BXGY line and refuse to reapply Friends & Family.
			if (hasPricingRules(item.pricing_rules)) {
				item.discount_percentage = 0;
				item.discount_amount = 0;
				item.pricing_rules = [];
				item.is_already_discounted = 0;
				item.is_accumulative_discount = 0;
				if (
					item.discount_source &&
					item.discount_source !== "manual_discount" &&
					item.discount_source !== COUPON_DISCOUNT_SOURCE &&
					!isFnfLine(item)
				) {
					item.discount_source = "";
				}
				recalculateItem(item);
			}
		});
		rebuildIncrementalCache();
	}

	async function removeOffer(offer, currentProfile = null, offersDialogRef = null) {
		const offerCode = typeof offer === "string" ? offer : offer?.name || offer?.code;

		// Cancel any pending auto-processing
		debouncedProcessOffers.cancel();

		if (!offerCode) {
			// Remove all offers - immediate operation, no queue needed
			offerQueue.cancel();

			appliedOffers.value = [];
			processFreeItems([]); // Remove all free items
			dropOfferDiscountsFromLines();
			applyHeaderDiscountFromServer(null);
			await nextTick();
			showSuccess(__("Offer has been removed from cart"));
			offersDialogRef?.resetApplyingState();
			return true;
		}

		const remainingOffers = appliedOffers.value.filter((entry) => entry.code !== offerCode);
		const remainingCodes = remainingOffers.map((entry) => entry.code);

		if (remainingCodes.length === 0) {
			// All offers removed - immediate operation
			offerQueue.cancel();

			appliedOffers.value = [];
			processFreeItems([]); // Remove all free items
			dropOfferDiscountsFromLines();
			applyHeaderDiscountFromServer(null);
			await nextTick();
			showSuccess(__("Offer has been removed from cart"));
			offersDialogRef?.resetApplyingState();
			return true;
		}

		let result = false;

		await offerQueue.enqueue(async (signal) => {
			if (signal?.aborted) return;

			try {
				offerProcessingState.value.isProcessing = true;
				offerProcessingState.value.error = null;

				const invoiceData = buildOfferEvaluationPayload(currentProfile);
				const pricedLines = snapshotPricedLines();
				const sentHash = generateCartHash();

				const response = await applyOffersResource.submit({
					invoice_data: invoiceData,
					selected_offers: remainingCodes,
				});

				if (signal?.aborted) return;

				// The cart changed while the request was in flight: the answer is dropped, and
				// the offer comes off the list and off its lines (so it cannot stay on them, or
				// come back offline); the next pass, the one the change queued, prices the cart
				// with the offers left (I-1r, m-r2-1).
				if (generateCartHash() !== sentHash) {
					appliedOffers.value = appliedOffers.value.filter((entry) =>
						remainingCodes.includes(entry.code)
					);
					releaseOfferFromLines(offerCode);
					result = true;
					return;
				}

				const {
					items: responseItems,
					freeItems,
					appliedRules,
					headerDiscount,
					friendsAndFamily,
				} = parseOfferResponse(response);

				applyDiscountsFromServer(responseItems, friendsAndFamily);
				processFreeItems(freeItems);
				applyHeaderDiscountFromServer(headerDiscount);
				filterActiveOffers(appliedRules);

				appliedOffers.value = appliedOffers.value.filter((entry) =>
					remainingCodes.includes(entry.code)
				);
				stampServerScopes(pricedLines);

				offerProcessingState.value.lastProcessedAt = Date.now();

				await nextTick();
				showSuccess(__("Offer has been removed from cart"));
				offersDialogRef?.resetApplyingState();
				result = true;
			} catch (error) {
				if (signal?.aborted) return;
				console.error("Error removing offer:", error);
				offerProcessingState.value.error = error.message;
				showError(__("Failed to update cart after removing offer."));
				offersDialogRef?.resetApplyingState();
				result = false;
			} finally {
				offerProcessingState.value.isProcessing = false;
			}
		});

		return result;
	}

	/**
	 * Validates applied offers and removes invalid ones when cart changes.
	 * This function is called from processOffersInternal - it does NOT manage
	 * @param {Object} currentProfile - Current POS profile
	 * @param {AbortSignal} signal - Optional abort signal for cancellation
	 * @returns {boolean} True if any offers were removed
	 */
	async function reapplyOffer(currentProfile, signal = null) {
		// Clear offers if cart is empty
		if (invoiceItems.value.length === 0 && appliedOffers.value.length) {
			appliedOffers.value = [];
			processFreeItems([]); // Remove all free items when cart is empty
			return true;
		}

		// Only validate if there are applied offers
		if (appliedOffers.value.length === 0 || invoiceItems.value.length === 0) {
			return false;
		}

		// Check if operation was cancelled
		if (signal?.aborted) return false;

		try {
			// Build current cart snapshot for validation
			const cartSnapshot = buildCartSnapshot();

			// Check each applied offer against current cart state
			const invalidOffers = [];
			for (const appliedOffer of appliedOffers.value) {
				const offer = appliedOffer.offer;
				if (!offer) continue;

				// Use offersStore to check eligibility
				offersStore.updateCartSnapshot(cartSnapshot);
				const { eligible, reason } = offersStore.checkOfferEligibility(offer);

				if (!eligible) {
					invalidOffers.push({
						...appliedOffer,
						reason,
					});
				}
			}

			// Check for cancellation
			if (signal?.aborted) return false;

			// If any offers are invalid, remove them and reapply remaining
			if (invalidOffers.length > 0) {
				const validOfferCodes = appliedOffers.value
					.filter((o) => !invalidOffers.find((inv) => inv.code === o.code))
					.map((o) => o.code);

				if (validOfferCodes.length === 0) {
					// All offers invalid - clear everything
					appliedOffers.value = [];
					processFreeItems([]);
					dropOfferDiscountsFromLines();
				} else {
					// Reapply only valid offers
					const invoiceData = buildOfferEvaluationPayload(currentProfile);
					const pricedLines = snapshotPricedLines();
					const response = await applyOffersResource.submit({
						invoice_data: invoiceData,
						selected_offers: validOfferCodes,
					});

					if (signal?.aborted) return false;

					const {
						items: responseItems,
						freeItems,
						appliedRules,
						headerDiscount,
						friendsAndFamily,
					} = parseOfferResponse(response);

					applyDiscountsFromServer(responseItems, friendsAndFamily);
					processFreeItems(freeItems);
					applyHeaderDiscountFromServer(headerDiscount);
					filterActiveOffers(appliedRules);

					// Update appliedOffers to only include valid ones
					appliedOffers.value = appliedOffers.value.filter((entry) =>
						appliedRules.includes(entry.code)
					);
					stampServerScopes(pricedLines);
				}

				// Wait for Vue to update before showing toast
				await nextTick();

				// The line's saving row disappears; the offers popup lists what the cart lacks
				rememberRemovedOffers(invalidOffers);
				return true;
			}
			return false;
		} catch (error) {
			if (signal?.aborted) return false;
			console.error("Error validating offers:", error);
			offerProcessingState.value.error = error.message;
			return false;
		}
	}

	/**
	 * Apply offers when offline using cached offer data.
	 * Calculates discounts client-side based on offer rules.
	 *
	 * In offline mode, we:
	 * 1. Check eligibility using posOffers.checkOfferEligibility
	 * 2. Apply discount percentage/amount directly to cart items
	 * 3. Handle free items (product discounts) via dedicated is_free_item rows (same as online)
	 * 4. Mark offers as applied (with source: "offline")
	 *
	 * Supports:
	 * - Discount Percentage (e.g., 10% off)
	 * - Discount Amount (e.g., $5 off)
	 * - Free Items (e.g., Buy 2 Get 1 Free)
	 */
	function applyOffersOffline() {
		// Skip if cart is empty or no offers available
		if (invoiceItems.value.length === 0 || !offersStore.hasFetched) {
			return;
		}

		// Verify we're actually offline
		if (!offlineState.isOffline) {
			return; // Use online mode instead
		}

		try {
			// Build current cart snapshot
			const cartSnapshot = buildCartSnapshot();
			offersStore.updateCartSnapshot(cartSnapshot);

			// Offers whose result depends on the whole cart (Min/Max) are priced again
			// on every change, or a qty change keeps a stale blended % (G7).
			const recomputed = recomputeAppliedOffersOffline();

			// Get eligible auto offers
			const eligibleOffers = offersStore.autoEligibleOffers;

			// Find new offers to apply (both price and product discounts)
			const appliedOfferCodes = new Set(appliedOffers.value.map((o) => o.code));
			const newOffers = eligibleOffers.filter((offer) => !appliedOfferCodes.has(offer.name));

			if (newOffers.length === 0) {
				if (recomputed) rebuildIncrementalCache();
				return;
			}

			const newlyAppliedOffers = [];

			const orderedOffers = [...newOffers].sort(
				(a, b) => offerStrategyOrder(b) - offerStrategyOrder(a)
			);

			for (const offer of orderedOffers) {
				// Determine offer type: "Item Price" (discount) or "Give Product" (free item)
				const isProductDiscount = offer.offer === "Give Product";

				const eligibleItems = offerScopeItems(offer);

				if (eligibleItems.length === 0) continue;

				let offerApplied = false;

				if (isProductDiscount) {
					// === PRODUCT DISCOUNT (FREE ITEMS) ===
					// Paid lines only: free gift rows must not qualify for (or seed) more gifts
					offerApplied = applyOfflineFreeItem(
						offer,
						eligibleItems.filter((item) => !item.is_free_item)
					);
				} else {
					// === PRICE DISCOUNT ===
					offerApplied = applyOfflinePriceDiscount(offer, eligibleItems);
				}

				if (offerApplied) {
					// Mark offer as applied
					appliedOffers.value.push({
						name: offer.title || offer.name,
						code: offer.name,
						offer,
						source: "offline",
						applied: true,
						rules: [offer.name],
						min_qty: offer.min_qty,
						max_qty: offer.max_qty,
						min_amt: offer.min_amt,
						max_amt: offer.max_amt,
					});

					newlyAppliedOffers.push(offer.title || offer.name);
				}
			}

			// Rebuild cache after bulk changes
			if (newlyAppliedOffers.length > 0 || recomputed) {
				rebuildIncrementalCache();
			}
			if (newlyAppliedOffers.length > 0) {
				showSuccess(__("Offline: {0} applied", [newlyAppliedOffers.join(", ")]));
			}
		} catch (error) {
			console.error("Error applying offers offline:", error);
		}
	}

	/** The cart lines (or `lines`) an offer's apply_on scope covers (offline). */
	function offerScopeItems(offer, lines = invoiceItems.value) {
		if (offer.apply_on === "Item Code") {
			const eligibleCodes = offer.eligible_items || [];
			return lines.filter((item) => eligibleCodes.includes(item.item_code));
		}
		if (offer.apply_on === "Item Group") {
			const eligibleGroups = offer.eligible_item_groups || [];
			return eligibleGroups.includes("All Item Groups")
				? lines
				: lines.filter((item) => eligibleGroups.includes(item.item_group));
		}
		if (offer.apply_on === "Brand") {
			const eligibleBrands = offer.eligible_brands || [];
			return lines.filter((item) => eligibleBrands.includes(item.brand));
		}
		// Transaction-level discount applies to all items
		if (offer.apply_on === "Transaction") return lines;
		return [];
	}

	/**
	 * Price again the applied offers whose strategy says its result depends on the
	 * whole cart (`recomputesOffline`, e.g. Min/Max), online- or offline-applied.
	 * One that no longer qualifies is taken off its lines and out of the applied list.
	 * @returns {boolean} True if any such offer was priced again
	 */
	function recomputeAppliedOffersOffline() {
		let recomputed = false;
		const kept = [];
		for (const entry of appliedOffers.value) {
			const offer =
				entry.offer || offersStore.availableOffers.find((o) => o.name === entry.code);
			const strategy = offer && getStrategyForOffer(offer);
			// Priced online by a cross-cart mode no strategy here can price again: its
			// blended % would go stale (a one-unit winner at 100% would ring 4 units
			// up at 0), so the offer comes off its lines, which sell at full price.
			if (!strategy && offer?.apply_discount_on_price) {
				// Its scope lines are as the server priced them: the server's price stands.
				if (entry.server_scope && entry.server_scope === offerScopeSignature(offer)) {
					kept.push(entry);
					continue;
				}
				warnUnhandledOfflineMode(offer);
				releaseOfferFromLines(entry.code);
				recomputed = true;
				continue;
			}
			if (!strategy?.recomputesOffline) {
				kept.push(entry);
				continue;
			}
			recomputed = true;
			const { eligible } = offersStore.checkOfferEligibility(offer);
			const ctx = { recalculateItem, invoiceItems: invoiceItems.value };
			if (strategy.apply(offer, eligible ? offerScopeItems(offer) : [], ctx)) {
				kept.push(entry);
			}
		}
		if (kept.length !== appliedOffers.value.length) appliedOffers.value = kept;
		return recomputed;
	}

	/**
	 * Take one offer off the lines carrying it, and its discount with it where it
	 * was the line's only rule. Coupon and F&F lines keep their own discount.
	 */
	function releaseOfferFromLines(offerCode) {
		for (const item of invoiceItems.value) {
			if (item.is_free_item || isCouponLine(item) || isFnfLine(item)) continue;
			const rules = normalizePricingRules(item.pricing_rules);
			if (!rules.includes(offerCode)) continue;
			const rest = rules.filter((name) => name !== offerCode);
			item.pricing_rules = rest;
			// A cashier's own discount is not the offer's: only the rule name comes off.
			if (rest.length === 0 && item.discount_source !== "manual_discount") {
				item.discount_percentage = 0;
				item.discount_amount = 0;
				item.is_already_discounted = 0;
				item.is_accumulative_discount = 0;
				item.discount_source = "";
			}
			recalculateItem(item);
		}
	}

	/**
	 * What an offer's price depends on, from its scope lines: item, qty, UOM and list
	 * price of each line, or for an offer summed per scope present
	 * (`accumulative_scope_field`) only which scope values are in the cart. Taken when
	 * the server prices the cart (`server_scope` on the applied entry), so offline an
	 * offer no strategy can price again keeps the server's price until its scope
	 * changes, e.g. a line outside the scope or a new customer leaves it alone (I-1).
	 */
	function offerScopeSignature(offer, cartLines = invoiceItems.value) {
		const lines = offerScopeItems(offer, cartLines).filter((item) => !item.is_free_item);
		const field = offer.accumulative_scope_field;
		if (field) {
			return JSON.stringify([...new Set(lines.map((item) => item[field]))].sort());
		}
		return JSON.stringify(
			lines.map((item) => [
				item.item_code,
				Number(item.quantity) || 0,
				item.uom || item.stock_uom || "",
				Number(item.price_list_rate) || 0,
			])
		);
	}

	/**
	 * Record each applied offer's scope as the server priced it (see offerScopeSignature):
	 * from `pricedLines`, the lines as they were when the request was built, never the
	 * cart after the answer arrived, or a change made while it was in flight would be
	 * signed as server-confirmed (I-1r).
	 */
	function stampServerScopes(pricedLines) {
		for (const entry of appliedOffers.value) {
			const offer =
				entry.offer || offersStore.availableOffers.find((o) => o.name === entry.code);
			if (offer) entry.server_scope = offerScopeSignature(offer, pricedLines);
		}
	}

	/** A copy of the cart lines a request is built from, for stampServerScopes. */
	function snapshotPricedLines() {
		return invoiceItems.value.map((item) => ({ ...item }));
	}

	/**
	 * Apply price discount (percentage or amount) to eligible items offline
	 * @param {Object} offer - The offer to apply
	 * @param {Array} eligibleItems - Items eligible for the discount
	 * @returns {boolean} True if discount was applied
	 */
	function applyOfflinePriceDiscount(offer, eligibleItems) {
		const strategy = getStrategyForOffer(offer);
		if (strategy) {
			return strategy.apply(offer, eligibleItems, {
				recalculateItem,
				invoiceItems: invoiceItems.value,
			});
		}
		// A cross-cart mode (Min, Max, Accumulative) with no strategy loaded must not
		// fall through to the flat %: that would put the rule's full % on every line
		// in scope (a "buy one free" rule rang up a whole line, or a whole group, at
		// 0). The offer is skipped and the lines sell at full price (G7).
		if (offer.apply_discount_on_price) {
			warnUnhandledOfflineMode(offer);
			return false;
		}

		const discountType = offer.discount_type || offer.rate_or_discount;
		const discountPercentage = Number.parseFloat(offer.discount_percentage) || 0;
		const discountAmount = Number.parseFloat(offer.discount_amount) || 0;
		const rate = Number.parseFloat(offer.rate) || 0;

		let applied = false;

		for (const item of eligibleItems) {
			const stacks =
				offer.promotion_type === "Auto Discount" && allowsAutoDiscountStacking(item);

			if (offer.promotion_type === "Auto Discount" && item.is_already_discounted && !stacks) {
				continue;
			}

			// Only apply if no existing pricing rule
			if (item.pricing_rules && item.pricing_rules.length > 0 && !stacks) continue;

			if (discountType === "Discount Percentage" && discountPercentage > 0) {
				if (stacks) {
					const base = Number.parseFloat(item.discount_percentage) || 0;
					const itemMax = Number.parseFloat(item.max_discount) || 0;
					const total = base + discountPercentage;
					item.discount_percentage = Math.min(total, itemMax > 0 ? itemMax : 100, 100);
					item.pricing_rules = [...(item.pricing_rules || []), offer.name];
				} else {
					item.discount_percentage = discountPercentage;
					item.pricing_rules = [offer.name];
				}
				recalculateItem(item);
				applied = true;
			} else if (discountType === "Discount Amount" && discountAmount > 0) {
				if (stacks) {
					// Accumulate, capped at the line's own value (never discount below zero).
					const effectiveRate =
						item.is_rate_manually_edited === 1
							? item.rate
							: item.price_list_rate || item.rate;
					const baseAmount =
						(Number.parseFloat(item.quantity) || 0) * (Number.parseFloat(effectiveRate) || 0);
					const existing = Number.parseFloat(item.discount_amount) || 0;
					item.discount_amount = Math.min(existing + discountAmount, baseAmount);
					item.pricing_rules = [...(item.pricing_rules || []), offer.name];
				} else {
					item.discount_amount = discountAmount;
					item.pricing_rules = [offer.name];
				}
				recalculateItem(item);
				applied = true;
			} else if (discountType === "Rate" && rate > 0) {
				if (stacks) {
					// Two fixed-rate overrides can't be added together — combining them
					// means the customer keeps whichever is more favorable (lower).
					const currentRate = Number.parseFloat(item.rate);
					item.rate = Number.isFinite(currentRate) ? Math.min(currentRate, rate) : rate;
					item.pricing_rules = [...(item.pricing_rules || []), offer.name];
				} else {
					item.rate = rate;
					item.pricing_rules = [offer.name];
				}
				recalculateItem(item);
				applied = true;
			}
		}

		return applied;
	}

	/**
	 * Apply free item (product discount) offer offline
	 * Handles: same_item (free item = purchased item) or specific free_item
	 *
	 * Satellite product types (Gift Pool, GWP) register via offerStrategies —
	 * this host only owns the plain free-item paths.
	 *
	 * Recursive logic:
	 * - recurse_for: Give free item for every N quantity
	 * - apply_recursion_over: Qty for which recursion isn't applicable
	 * - Example: recurse_for=2, apply_recursion_over=0, free_qty=1
	 *   -> For 6 items: (6-0)/2 * 1 = 3 free items
	 *
	 * @param {Object} offer - The offer to apply
	 * @param {Array} eligibleItems - Items eligible for the free item
	 * @returns {boolean} True if free item was applied
	 */
	function applyOfflineFreeItem(offer, eligibleItems) {
		const strategy = getProductStrategyForOffer(offer);
		if (strategy) {
			return strategy.apply(offer, eligibleItems, {
				recalculateItem,
				invoiceItems: invoiceItems.value,
			});
		}
		const freeQty = Number.parseFloat(offer.free_qty) || 0;
		const sameItem = offer.same_item === 1;
		const isRecursive = offer.is_recursive === 1;
		const recurseFor = Number.parseFloat(offer.recurse_for) || 0;
		const applyRecursionOver = Number.parseFloat(offer.apply_recursion_over) || 0;
		const freeItemCode = offer.free_item;

		if (freeQty <= 0) return false;

		let applied = false;

		if (sameItem) {
			// Free item is the same as the purchased item
			// E.g., "Buy 2 Get 1 Free" - the free item is the same item
			for (const item of eligibleItems) {
				let freeItemsToGive = freeQty;
				const minQty = Number.parseFloat(offer.min_qty) || 0;

				// Mirrors posnext_promotions get_gwp_same_item_free_qty: paid qty must
				// meet min_qty; the gift is added on top (never carved from paid qty).
				if (minQty > 0 && item.quantity < minQty) {
					freeItemsToGive = 0;
				} else if (isRecursive && recurseFor > 0) {
					// Recursive: for every recurseFor quantity, give freeQty free
					// Formula: floor((qty - apply_recursion_over) / recurse_for) * free_qty
					// E.g., Buy 2 Get 1 Free: recurse_for=2, free_qty=1
					//   For 6 items: floor((6-0)/2) * 1 = 3 free items
					const effectiveQty = Math.max(0, item.quantity - applyRecursionOver);
					const multiplier = Math.floor(effectiveQty / recurseFor);
					freeItemsToGive = multiplier * freeQty;
				} else if (!isRecursive && offer.min_qty > 0) {
					// Non-recursive: just check if min_qty is met, give freeQty once
					// E.g., Buy 2 Get 1 Free (non-recursive): for 6 items, still give 1 free
					if (item.quantity >= offer.min_qty) {
						freeItemsToGive = freeQty;
					} else {
						freeItemsToGive = 0;
					}
				}

				if (freeItemsToGive <= 0) {
					continue;
				}
				const uomKey = item.uom || item.stock_uom;
				const existingFreeRow = invoiceItems.value.find(
					(r) =>
						r.is_free_item &&
						r.item_code === item.item_code &&
						(r.uom || r.stock_uom) === uomKey
				);
				if (existingFreeRow) {
					existingFreeRow.quantity = freeItemsToGive;
					existingFreeRow.free_qty = freeItemsToGive;
					const prArr = normalizePricingRules(existingFreeRow.pricing_rules);
					if (!prArr.includes(offer.name)) prArr.push(offer.name);
					existingFreeRow.pricing_rules = prArr;
				} else {
					invoiceItems.value.push({
						item_code: item.item_code,
						item_name: item.item_name || item.item_code,
						rate: 0,
						price_list_rate: 0,
						quantity: freeItemsToGive,
						discount_amount: 0,
						discount_percentage: 0,
						tax_amount: 0,
						amount: 0,
						stock_qty: 0,
						uom: uomKey,
						stock_uom: item.stock_uom || uomKey,
						conversion_factor: item.conversion_factor || 1,
						is_free_item: 1,
						free_qty: freeItemsToGive,
						pricing_rules: [offer.name],
						warehouse: item.warehouse,
						sales_person: item.sales_person || null,
						sales_person_name: item.sales_person_name || null,
					});
				}
				applied = true;
			}
		} else if (freeItemCode) {
			// Free item is a specific different item
			// Find if the free item is already in the cart
			const freeItemInCart = invoiceItems.value.find(
				(item) => item.item_code === freeItemCode
			);

			if (freeItemInCart) {
				// Calculate free qty (same recursive logic applies)
				let freeItemsToGive = freeQty;

				if (isRecursive && recurseFor > 0) {
					// Calculate based on total eligible quantity
					const totalEligibleQty = eligibleItems.reduce(
						(sum, item) => sum + (item.quantity || 0),
						0
					);
					const effectiveQty = Math.max(0, totalEligibleQty - applyRecursionOver);
					const multiplier = Math.floor(effectiveQty / recurseFor);
					freeItemsToGive = multiplier * freeQty;
				}

				// Mark existing cart item as having free quantity
				if (
					freeItemsToGive > 0 &&
					(!freeItemInCart.free_qty || freeItemInCart.free_qty === 0)
				) {
					freeItemInCart.free_qty = freeItemsToGive;
					freeItemInCart.pricing_rules = freeItemInCart.pricing_rules || [];
					if (!freeItemInCart.pricing_rules.includes(offer.name)) {
						freeItemInCart.pricing_rules.push(offer.name);
					}
					applied = true;
				}
			}
			// Note: We don't add new items to cart offline - that would require
			// fetching item details. The free item will be added when back online.
		}

		return applied;
	}

	/**
	 * Gross and net amount of a single cart line, on the same basis the server
	 * uses when gating min_amt/max_amt.
	 *
	 * Mirrors buildOfferEvaluationPayload (which sends
	 * `price_list_rate: item.price_list_rate || item.rate`) and the net-rate
	 * derivation in apply_offers, which folds item discounts back into the
	 * pricing items as `price_list_rate * (1 - discount_percentage / 100)`
	 * before handing the cart total to ERPNext's transaction engine.
	 */
	function offerLineAmounts(item) {
		const qty = item.quantity || 0;
		const listRate = Number.parseFloat(item.price_list_rate || item.rate) || 0;
		const gross = qty * listRate;
		const discountPct = Number.parseFloat(item.discount_percentage) || 0;
		return { gross, net: gross * (1 - discountPct / 100) };
	}

	/** Cart total after item-level discounts — the server's `doc.total`. */
	function offerNetSubtotal(items) {
		return items.reduce((sum, item) => sum + offerLineAmounts(item).net, 0);
	}

	/**
	 * Builds cart snapshot for offer validation.
	 * Paid lines only — free gifts must not inflate min_qty/max_qty/min_amt checks.
	 */
	function buildCartSnapshot() {
		const items = withCarvedQtyRestored(invoiceItems.value).filter((item) => !item.is_free_item);
		const totalQty = items.reduce((sum, item) => sum + (item.quantity || 0), 0);
		const itemCodes = items.map((item) => item.item_code);
		const itemGroups = items.map((item) => item.item_group).filter(Boolean);
		const brands = items.map((item) => item.brand).filter(Boolean);

		// Build quantity maps for accurate offer validation
		// itemQuantities: { item_code: total_qty } - quantity per item code
		const itemQuantities = {};
		// itemGroupQuantities: { item_group: total_qty } - quantity per item group
		const itemGroupQuantities = {};
		// brandQuantities: { brand: total_qty } - quantity per brand
		const brandQuantities = {};
		// Gross line amounts (qty * price_list_rate) per scope, for min_amt/max_amt
		const itemAmounts = {};
		const itemGroupAmounts = {};
		const brandAmounts = {};

		for (const item of items) {
			const qty = item.quantity || 0;
			const { gross } = offerLineAmounts(item);

			// Aggregate by item code
			if (item.item_code) {
				itemQuantities[item.item_code] = (itemQuantities[item.item_code] || 0) + qty;
				itemAmounts[item.item_code] = (itemAmounts[item.item_code] || 0) + gross;
			}

			// Aggregate by item group
			if (item.item_group) {
				itemGroupQuantities[item.item_group] =
					(itemGroupQuantities[item.item_group] || 0) + qty;
				itemGroupAmounts[item.item_group] =
					(itemGroupAmounts[item.item_group] || 0) + gross;
			}

			// Aggregate by brand
			if (item.brand) {
				brandQuantities[item.brand] = (brandQuantities[item.brand] || 0) + qty;
				brandAmounts[item.brand] = (brandAmounts[item.brand] || 0) + gross;
			}
		}

		return {
			subtotal: subtotal.value,
			itemCount: totalQty,
			itemCodes: [...new Set(itemCodes)],
			itemGroups: [...new Set(itemGroups)],
			brands: [...new Set(brands)],
			// Quantity maps for accurate min_qty/max_qty validation
			itemQuantities,
			itemGroupQuantities,
			brandQuantities,
			// Amount bases for min_amt/max_amt validation
			netSubtotal: offerNetSubtotal(items),
			itemAmounts,
			itemGroupAmounts,
			brandAmounts,
		};
	}

	/**
	 * Find a cart item by item_code and optionally by UOM
	 * @param {string} itemCode - Item code to find
	 * @param {string|null} uom - Optional UOM to match
	 * @returns {Object|undefined} Cart item or undefined
	 */
	function findCartItem(itemCode, uom = null, isFreeItem = undefined) {
		return invoiceItems.value.find((item) => {
			if (item.item_code !== itemCode) return false;
			if (uom && item.uom !== uom) return false;
			// When same SKU has paid + free rows, match the intended line.
			if (
				isFreeItem !== undefined &&
				Boolean(item.is_free_item) !== Boolean(isFreeItem)
			) {
				return false;
			}
			return true;
		});
	}

	/**
	 * Find an existing cart item with target UOM (for merge detection)
	 * @param {string} itemCode - Item code
	 * @param {string} targetUom - Target UOM to find
	 * @param {Object} excludeItem - Item to exclude from search
	 * @returns {Object|undefined} Existing item or undefined
	 */
	function findItemWithUom(itemCode, targetUom, excludeItem = null) {
		return invoiceItems.value.find(
			(item) =>
				item.item_code === itemCode &&
				item.uom === targetUom &&
				item !== excludeItem &&
				// Never merge a paid line into (or from) a free promo row
				!item.is_free_item &&
				!excludeItem?.is_free_item
		);
	}

	/**
	 * Remove an item from the cart
	 * @param {Object} cartItem - Item to remove
	 */
	function removeCartItem(cartItem) {
		const index = invoiceItems.value.indexOf(cartItem);
		if (index > -1) {
			invoiceItems.value.splice(index, 1);
		}
	}

	/**
	 * Merge source item into target item
	 * @param {Object} sourceItem - Item to merge from (will be removed)
	 * @param {Object} targetItem - Item to merge into
	 * @param {number} quantity - Quantity to add to target
	 * @returns {number} New total quantity
	 */
	function mergeItems(sourceItem, targetItem, quantity) {
		targetItem.quantity += quantity;
		recalculateItem(targetItem);
		removeCartItem(sourceItem);
		rebuildIncrementalCache();
		return targetItem.quantity;
	}

	/**
	 * Apply UOM metadata and pricing.
	 * Free / promo / manually-edited rates must NOT be replaced from the price
	 * list — that path bypasses the same lock as free-item rate editing (#1/#5).
	 * @param {Object} cartItem - Cart item to update
	 * @param {string} newUom - New UOM
	 * @param {number} qty - Quantity for pricing
	 */
	async function applyUomChange(cartItem, newUom, qty) {
		if (isFreePromoRow(cartItem)) {
			throw new Error(__("Free promotional items cannot be edited"));
		}

		const uomData = cartItem.item_uoms?.find((u) => u.uom === newUom);
		const conversionFactor = uomData?.conversion_factor || 1;
		const oldConversion = cartItem.conversion_factor || 1;

		cartItem.uom = newUom;
		cartItem.conversion_factor = conversionFactor;

		if (shouldPreserveRateOnUomChange(cartItem)) {
			cartItem.rate = scaleRateForUomChange(cartItem.rate, oldConversion, conversionFactor);
			cartItem.price_list_rate = scaleRateForUomChange(
				cartItem.price_list_rate,
				oldConversion,
				conversionFactor
			);
			return;
		}

		const pricing = await resolveUomPricing(cartItem, newUom, conversionFactor, qty);
		cartItem.rate = pricing.rate;
		cartItem.price_list_rate = pricing.price_list_rate;
	}

	/**
	 * Change item UOM - merges if target UOM already exists
	 * @param {string} itemCode - Item code
	 * @param {string} newUom - New UOM to change to
	 * @param {string|null} currentUom - Current UOM (required when same item has multiple UOMs)
	 */
	async function changeItemUOM(itemCode, newUom, currentUom = null) {
		try {
			const cartItem = findCartItem(itemCode, currentUom, false);
			if (!cartItem || cartItem.uom === newUom) return;
			if (isFreePromoRow(cartItem)) {
				showError(__("Free promotional items cannot be edited"));
				return;
			}

			// Check for existing item to merge with
			const existingItem = findItemWithUom(itemCode, newUom, cartItem);
			if (existingItem) {
				const totalQty = mergeItems(cartItem, existingItem, cartItem.quantity);
				showSuccess(__("Merged into {0} (Total: {1})", [newUom, totalQty]));
				return;
			}

			// Apply UOM change
			await applyUomChange(cartItem, newUom, cartItem.quantity);
			recalculateItem(cartItem);
			rebuildIncrementalCache();
			showSuccess(__("Unit changed to {0}", [newUom]));
		} catch (error) {
			console.error("Error changing UOM:", error);
			showError(parseError(error) || __("Failed to update UOM. Please try again."));
		}
	}

	/**
	 * Update item details - handles UOM changes with merging
	 * @param {string} itemCode - Item code
	 * @param {Object} updates - Updated details
	 * @param {string|null} currentUom - Current UOM (required when same item has multiple UOMs)
	 */
	async function updateItemDetails(itemCode, updates, currentUom = null) {
		try {
			const cartItem = findCartItem(itemCode, currentUom, updates?.is_free_item);
			if (!cartItem) {
				throw new Error("Item not found in cart");
			}

			// Free / GWP rows are owned by the promotion engine — refuse
			// cashier edits that would inflate free qty or change rate/UOM.
			if (cartItem.is_free_item) {
				throw new Error(__("Free promotional items cannot be edited"));
			}

			// Handle UOM change with potential merge
			if (updates.uom && updates.uom !== cartItem.uom) {
				const existingItem = findItemWithUom(itemCode, updates.uom, cartItem);
				if (existingItem) {
					const qtyToMerge = updates.quantity ?? cartItem.quantity;
					const totalQty = mergeItems(cartItem, existingItem, qtyToMerge);
					showSuccess(__("Merged into {0} (Total: {1})", [updates.uom, totalQty]));
					return true;
				}

				// Apply UOM change with new rate
				try {
					await applyUomChange(
						cartItem,
						updates.uom,
						updates.quantity ?? cartItem.quantity
					);
				} catch {
					// Fallback: just change UOM without rate update
					cartItem.uom = updates.uom;
				}
			}

			// Validate stock if quantity is being increased
			if (
				updates.quantity !== undefined &&
				updates.quantity > cartItem.quantity &&
				settingsStore.shouldEnforceStockValidation() &&
				shouldValidateItemStock(cartItem)
			) {
				const otherLinesQty =
					getCartStockQtyForItem(invoiceItems.value, cartItem.item_code) -
					rowStockQty(cartItem);
				const totalQty = otherLinesQty + rowStockQty(cartItem, updates.quantity);
				const check = checkStockAvailability(cartItem, totalQty);
				if (!check.available) {
					throw new Error(check.error);
				}
			}

			// Friends & Family lines: the % comes from F&F Settings and the
			// server re-decides it on every evaluation — never a cashier edit.
			const isFnf = isFnfLine(cartItem);

			// Apply other updates
			if (updates.quantity !== undefined) cartItem.quantity = updates.quantity;
			if (updates.warehouse !== undefined) cartItem.warehouse = updates.warehouse;
			if (updates.discount_percentage !== undefined && !isFnf)
				cartItem.discount_percentage = updates.discount_percentage;
			if (updates.discount_amount !== undefined && !isFnf) {
				cartItem.discount_amount = updates.discount_amount;
				// What the cashier typed is the request, even the figure the line showed (G8).
				cartItem._unit_discount_amount = null;
			}
			if (updates.rate !== undefined) cartItem.rate = updates.rate;
			if (updates.price_list_rate !== undefined)
				cartItem.price_list_rate = updates.price_list_rate;
			if (updates.serial_no !== undefined) cartItem.serial_no = updates.serial_no;
			// Track manual rate edits for audit purposes
			if (updates.is_rate_manually_edited !== undefined)
				cartItem.is_rate_manually_edited = updates.is_rate_manually_edited;
			if (updates.original_rate !== undefined)
				cartItem.original_rate = updates.original_rate;
			if (updates.sales_person !== undefined) {
				cartItem.sales_person = updates.sales_person || null;
				cartItem.sales_person_name = updates.sales_person
					? updates.sales_person_name || updates.sales_person
					: null;
			}

			recalculateItem(cartItem);
			rebuildIncrementalCache();
			showSuccess(__("{0} updated", [cartItem.item_name]));
			return true;
		} catch (error) {
			console.error("Error updating item:", error);
			showError(parseError(error) || __("Failed to update item."));
			return false;
		}
	}

	// Performance: Cache previous item codes hash to avoid unnecessary recalculations
	let previousItemCodesHash = "";
	let cachedItemCodes = [];
	let cachedItemGroups = [];
	let cachedBrands = [];
	let cachedItemQuantities = {};
	let cachedItemGroupQuantities = {};
	let cachedBrandQuantities = {};
	let cachedItemAmounts = {};
	let cachedItemGroupAmounts = {};
	let cachedBrandAmounts = {};

	function syncOfferSnapshot() {
		// Only sync if values are initialized
		if (subtotal.value !== undefined && invoiceItems.value) {
			// Paid lines only — free gifts must not inflate min_qty/max_qty checks
			const paidItems = withCarvedQtyRestored(invoiceItems.value).filter(
				(item) => !item.is_free_item
			);

			// Create hash for paid item codes and quantities to detect actual changes.
			// price_list_rate is part of the key because the cached amount maps
			// below are money, not just counts — a price list change with an
			// otherwise identical cart must invalidate them.
			const currentHash = paidItems
				.map(
					(item) =>
						`${item.item_code}:${item.quantity}:${item.price_list_rate || item.rate}`
				)
				.join(",");

			// Only recalculate expensive operations if items actually changed
			if (currentHash !== previousItemCodesHash) {
				cachedItemCodes = paidItems.map((item) => item.item_code);
				cachedItemGroups = [
					...new Set(paidItems.map((item) => item.item_group).filter(Boolean)),
				];
				cachedBrands = [
					...new Set(paidItems.map((item) => item.brand).filter(Boolean)),
				];

				// Build quantity maps for accurate offer validation
				cachedItemQuantities = {};
				cachedItemGroupQuantities = {};
				cachedBrandQuantities = {};
				cachedItemAmounts = {};
				cachedItemGroupAmounts = {};
				cachedBrandAmounts = {};

				for (const item of paidItems) {
					const qty = item.quantity || 0;
					const { gross } = offerLineAmounts(item);

					if (item.item_code) {
						cachedItemQuantities[item.item_code] =
							(cachedItemQuantities[item.item_code] || 0) + qty;
						cachedItemAmounts[item.item_code] =
							(cachedItemAmounts[item.item_code] || 0) + gross;
					}
					if (item.item_group) {
						cachedItemGroupQuantities[item.item_group] =
							(cachedItemGroupQuantities[item.item_group] || 0) + qty;
						cachedItemGroupAmounts[item.item_group] =
							(cachedItemGroupAmounts[item.item_group] || 0) + gross;
					}
					if (item.brand) {
						cachedBrandQuantities[item.brand] =
							(cachedBrandQuantities[item.brand] || 0) + qty;
						cachedBrandAmounts[item.brand] =
							(cachedBrandAmounts[item.brand] || 0) + gross;
					}
				}

				previousItemCodesHash = currentHash;
			}

			// Calculate total quantity (sum of all paid item quantities, not line count)
			const totalQty = paidItems.reduce((sum, item) => {
				return sum + (item.quantity || 0);
			}, 0);

			offersStore.updateCartSnapshot({
				subtotal: subtotal.value,
				itemCount: totalQty, // Total quantity, not number of line items
				itemCodes: cachedItemCodes,
				itemGroups: cachedItemGroups,
				brands: cachedBrands,
				itemQuantities: cachedItemQuantities,
				itemGroupQuantities: cachedItemGroupQuantities,
				brandQuantities: cachedBrandQuantities,
				// Recomputed every sync, not cached with the maps above: item
				// discounts change without any item/qty/price change (the server
				// stamps them back onto the cart after apply_offers).
				netSubtotal: offerNetSubtotal(paidItems),
				itemAmounts: cachedItemAmounts,
				itemGroupAmounts: cachedItemGroupAmounts,
				brandAmounts: cachedBrandAmounts,
			});
		}
	}

	/**
	 * Core offer processing function that validates and auto-applies offers.
	 * Runs through the queue to ensure sequential execution.
	 * Uses offline mode when network is unavailable.
	 * @param {AbortSignal} signal - Abort signal for cancellation
	 * @param {number} generation - Cart generation when this was triggered
	 * @param {boolean} force - If true, process even if cart hash matches
	 */
	async function processOffersInternal(signal = null, generation = 0, force = false) {
		// Check cancellation early
		if (signal?.aborted) return;

		// Check if this operation is stale (cart changed since this was queued)
		if (generation > 0 && generation < cartGeneration) {
			return; // Skip stale operation
		}

		// Only process offers if we have a POS profile
		// posProfile.value is the profile NAME (a string), not an object
		if (!posProfile.value) {
			return;
		}

		// POS Profile ignore_pricing_rule: no pricing rule applies. F&F is not a pricing
		// rule: the server still prices it on save, so the cart shows it too (D-R3-11).
		const shiftStore = usePOSShiftStore();
		if (shiftStore.currentProfile?.ignore_pricing_rule) {
			if (offlineState.isOffline) return;
			try {
				await refreshFriendsAndFamilyEligibility();
				if (signal?.aborted || (generation > 0 && generation < cartGeneration)) return;
				await evaluateFriendsAndFamilyOnly(
					{ customer: customer.value?.name || customer.value },
					signal,
					generation
				);
			} catch (error) {
				if (signal?.aborted) return;
				console.error("Error applying Friends & Family:", error);
				offerProcessingState.value.error = error.message;
			}
			return;
		}

		// Ensure offers are fetched before processing
		// This is critical for mobile view where InvoiceCart may not be mounted yet
		// IMPORTANT: This must happen BEFORE hash check, because if offers weren't
		// fetched on previous runs, we need to re-process even if cart hash matches
		const wasFetched = offersStore.hasFetched;
		// posProfile.value is the profile name string directly
		const profileName = posProfile.value;
		await offersStore.ensureOffersFetched(profileName);

		// Check cancellation after fetch
		if (signal?.aborted) return;

		// One-time-per-customer eligibility depends on async context (server
		// redemptions + identified flag). Await here so we never evaluate offers
		// before the customer gate is ready — setCustomer() alone can lose the
		// race with the debounced cart/customer watcher below.
		await Promise.all([
			syncOneTimeContextForCurrentCustomer(),
			// PN-130: cached per customer, so this is a no-op after setCustomer().
			refreshFriendsAndFamilyEligibility(),
		]);

		// Check cancellation after one-time context fetch
		if (signal?.aborted) return;

		// Generate current cart hash
		const currentHash = generateCartHash();

		// Skip if cart hasn't changed since last successful processing (unless forced)
		// Also force re-processing if offers were just fetched for the first time
		const justFetched = !wasFetched && offersStore.hasFetched;
		if (!force && !justFetched && currentHash === offerProcessingState.value.lastCartHash) {
			return;
		}

		// Update offer snapshot for eligibility checking
		syncOfferSnapshot();

		// === OFFLINE MODE ===
		// When offline, use cached offers and apply discounts client-side
		if (offlineState.isOffline) {
			applyOffersOffline();
			offerProcessingState.value.lastCartHash = generateCartHash();
			offerProcessingState.value.lastProcessedAt = Date.now();
			return;
		}

		// === ONLINE MODE ===
		// Get current profile from posProfile
		const currentProfile = {
			customer: customer.value?.name || customer.value,
			company: posProfile.value.company,
			selling_price_list: posProfile.value.selling_price_list,
			currency: posProfile.value.currency,
		};
		// True once apply_offers ran this pass (it evaluates F&F as well).
		let evaluatedOnServer = false;
		try {
			// 1. Identify invalid offers to remove (client-side check)
			const invalidOffers = [];

			for (const entry of appliedOffers.value) {
				if (entry.offer) {
					const { eligible } = offersStore.checkOfferEligibility(entry.offer);
					if (!eligible) invalidOffers.push(entry);
				}
			}

			// 2. Identify new eligible offers to apply (client-side check)
			const allEligibleOffers = offersStore.allEligibleOffers;
			const currentAppliedCodes = new Set(appliedOffers.value.map((o) => o.code));
			const newOffers = allEligibleOffers.filter(
				(offer) =>
					!currentAppliedCodes.has(offer.name) && !wasRemovedForCurrentCart(offer.name)
			);

			// 3. Determine if we need to call the server
			// We MUST hit the server if:
			// - We have applied offers
			// - We have new auto-offers to apply
			// - We have invalid offers to remove
			const invalidCodes = new Set(invalidOffers.map((o) => o.code));
			const validExistingCodes = appliedOffers.value
				.filter((o) => !invalidCodes.has(o.code))
				.map((o) => o.code);

			const newOfferCodes = newOffers.map((o) => o.name);
			const combinedCodes = [...new Set([...validExistingCodes, ...newOfferCodes])];

			// All applied offers became invalid and no new offers to apply.
			if (combinedCodes.length === 0 && invalidOffers.length > 0) {
				appliedOffers.value = [];
				processFreeItems([]);
				dropOfferDiscountsFromLines();
				// Also clear any transaction-level header discount the server
				// previously surfaced — if no offers remain, no header discount applies.
				applyHeaderDiscountFromServer(null);

				rememberRemovedOffers(invalidOffers);
			} else if (combinedCodes.length > 0) {
				const invoiceData = buildOfferEvaluationPayload(currentProfile);
				const pricedLines = snapshotPricedLines();
				const response = await applyOffersResource.submit({
					invoice_data: invoiceData,
					selected_offers: combinedCodes,
				});

				// Check for cancellation or stale operation
				if (signal?.aborted || (generation > 0 && generation < cartGeneration)) return;

				const {
					items: responseItems,
					freeItems,
					appliedRules,
					headerDiscount,
					friendsAndFamily,
				} = parseOfferResponse(response);

				// 4. Update cart items with new discounts

				applyDiscountsFromServer(responseItems, friendsAndFamily);
				evaluatedOnServer = true;
				processFreeItems(freeItems);
				applyHeaderDiscountFromServer(headerDiscount);

				// 5. Update appliedOffers list based on server confirmation
				const actuallyApplied = new Set(appliedRules);
				const nextAppliedOffers = [];

				// Handle existing ones
				for (const entry of appliedOffers.value) {
					if (
						!invalidOffers.find((inv) => inv.code === entry.code) &&
						actuallyApplied.has(entry.code)
					) {
						nextAppliedOffers.push(entry);
					}
				}

				// Handle new ones
				for (const offer of newOffers) {
					if (actuallyApplied.has(offer.name)) {
						nextAppliedOffers.push({
							name: offer.title || offer.name,
							code: offer.name,
							offer,
							source: "auto",
							applied: true,
							rules: [offer.name],
							min_qty: offer.min_qty,
							max_qty: offer.max_qty,
							min_amt: offer.min_amt,
							max_amt: offer.max_amt,
						});
					}
				}

				appliedOffers.value = nextAppliedOffers;
				stampServerScopes(pricedLines);

				// 6. UI Feedback
				if (invalidOffers.length > 0) {
					rememberRemovedOffers(invalidOffers);
				}
				// Newly applied offers show as savings on their cart lines
			} else if (invoiceItems.value.length === 0 && appliedOffers.value.length > 0) {
				// Cart cleared, reset offers
				appliedOffers.value = [];
				processFreeItems([]);
				rebuildIncrementalCache();
			}

			// PN-130: apply_offers was not needed for promotions — still let the
			// server apply (or strip) Friends & Family on this cart.
			if (!evaluatedOnServer) {
				await evaluateFriendsAndFamilyOnly(currentProfile, signal, generation);
				if (signal?.aborted || (generation > 0 && generation < cartGeneration)) return;
			}
			// Update last processed hash on success
			offerProcessingState.value.lastCartHash = generateCartHash();
			offerProcessingState.value.lastProcessedAt = Date.now();
			offerProcessingState.value.retryCount = 0;
		} catch (error) {
			if (signal?.aborted) return;
			console.error("Error in offer synchronization:", error);
			offerProcessingState.value.error = error.message;
		}
	}

	/**
	 * Triggers offer processing with proper state management.
	 * @param {boolean} force - If true, bypass hash check and force processing
	 */
	function triggerOfferProcessing(force = false) {
		// The cart of an unanswered submit is not re-priced: changed rows would give it a
		// new key, and so a second sale (F6). Any edit of the cart lifts this.
		if (hasUnresolvedSubmit()) return;
		// Increment generation to invalidate any in-flight operations
		const currentGen = ++cartGeneration;

		// Enqueue the processing task - queue handles concurrency
		offerQueue.enqueue(async (signal) => {
			try {
				offerProcessingState.value.isProcessing = true;
				offerProcessingState.value.isAutoProcessing = true;
				offerProcessingState.value.error = null;

				await processOffersInternal(signal, currentGen, force);
			} catch (error) {
				if (!signal?.aborted) {
					console.error("Error in offer processing:", error);
					offerProcessingState.value.error = error.message;
					offerProcessingState.value.retryCount++;

					// Auto-retry on failure (max 3 times)
					if (offerProcessingState.value.retryCount < 3) {
						setTimeout(() => {
							triggerOfferProcessing(true);
						}, 500 * offerProcessingState.value.retryCount);
					}
				}
			} finally {
				offerProcessingState.value.isProcessing = false;
				offerProcessingState.value.isAutoProcessing = false;
			}
		});
	}

	/**
	 * Force refresh offers - clears state and reprocesses from scratch.
	 * Call this when you suspect offers are out of sync.
	 */
	function forceRefreshOffers() {
		// Cancel any pending operations
		debouncedProcessOffers.cancel();
		offerQueue.cancel();

		// Clear the hash to force reprocessing
		offerProcessingState.value.lastCartHash = "";
		offerProcessingState.value.error = null;
		offerProcessingState.value.retryCount = 0;

		// Trigger immediate processing
		triggerOfferProcessing(true);
	}

	/**
	 * Calculate dynamic debounce delay based on cart size.
	 * Small carts (1-3 items): 100ms - fast response
	 * Medium carts (4-10 items): 200ms - balanced
	 * Large carts (11+ items): 300ms - reduce API load
	 */
	function getDynamicDebounceDelay() {
		const itemCount = invoiceItems.value.length;
		if (itemCount <= 3) return 100;
		if (itemCount <= 10) return 200;
		return 300;
	}

	/**
	 * Debounced offer processing with dynamic delay based on cart size.
	 * Prevents race conditions while staying responsive for small carts.
	 */
	let debounceTimeoutId = null;
	function debouncedProcessOffers() {
		if (debounceTimeoutId) {
			clearTimeout(debounceTimeoutId);
		}
		debounceTimeoutId = setTimeout(() => {
			debounceTimeoutId = null;
			triggerOfferProcessing(false);
		}, getDynamicDebounceDelay());
	}

	// Add cancel and flush methods for compatibility
	debouncedProcessOffers.cancel = () => {
		if (debounceTimeoutId) {
			clearTimeout(debounceTimeoutId);
			debounceTimeoutId = null;
		}
	};

	debouncedProcessOffers.flush = () => {
		if (debounceTimeoutId) {
			clearTimeout(debounceTimeoutId);
			debounceTimeoutId = null;
			triggerOfferProcessing(false);
		}
	};

	// "Create Only Sales Order" turned on (or loaded after the cart): the open cart
	// becomes a Sales Order, its F&F stripped as the Order switch strips it (D-R3-12).
	watch(
		() => settingsStore.createOnlySalesOrder,
		(only) => {
			if (only) setTargetDoctype("Sales Order");
		},
		{ immediate: true }
	);

	// Watch for ANY cart changes that might affect offer eligibility
	// This includes: items, quantities, customer, subtotal, etc.
	watch(
		[
			// Watch item count (additions/removals)
			() => invoiceItems.value.length,
			// Watch item details (quantity, code, uom changes)
			() =>
				invoiceItems.value
					.map(
						(item) =>
							`${item.item_code}:${item.quantity}:${item.uom || ""}:${
								item.discount_percentage || 0
							}`
					)
					.join(","),
			// Watch subtotal changes
			subtotal,
			// Watch customer changes (some offers are customer-specific)
			() => customer.value?.name || customer.value,
		],
		(_newVals, oldVals) => {
			// Skip if this is initial render with empty cart
			if (!oldVals && invoiceItems.value.length === 0) {
				return;
			}

			// Use debounced processing to prevent race conditions
			// This batches rapid cart changes and ensures only one offer
			// processing operation runs at a time
			debouncedProcessOffers();
		},
		{ immediate: true, flush: "post" }
	);

	// Re-check a scoped coupon when the paid lines (qty, UOM, price, manual rate) or the customer change.
	watch(
		() =>
			isLineLevelCoupon(appliedCoupon.value)
				? `${invoiceItems.value
						.filter((item) => !item.is_free_item)
						.map(
							(item) =>
								`${item.item_code}:${item.quantity}:${item.uom || ""}:${item.price_list_rate || 0}:${
									item.is_rate_manually_edited ? item.rate : ""
								}`
						)
						.join(",")}::${customer.value?.name || customer.value || ""}`
				: null,
		(key, oldKey) => {
			if (!key || !oldKey || key === oldKey) return;
			capFixedCouponLines();
			scheduleCouponRevalidation();
		}
	);

	// An emptied cart drops its whole-cart coupon, which would otherwise push the total below zero
	watch(
		() => invoiceItems.value.some((item) => !item.is_free_item),
		(hasPaidItems) => {
			if (hasPaidItems || !appliedCoupon.value || isLineLevelCoupon(appliedCoupon.value)) return;
			removeDiscount();
			appliedCoupon.value = null;
		}
	);

	/** Re-check a whole-cart coupon for the customer; say why when it is dropped. */
	async function revalidateWholeCartCoupon(coupon, name) {
		const result = name
			? await call(promoApi.validateCoupon(), {
					coupon_code: coupon.code,
					customer: name,
					company: usePOSShiftStore().currentProfile?.company,
					target_doctype: targetDoctype.value,
				}).catch(() => ({ valid: true }))
			: { valid: false, message: __("No customer selected") };
		if (result?.valid || appliedCoupon.value !== coupon) return;
		removeDiscount();
		appliedCoupon.value = null;
		showWarning(
			__("Coupon {0} removed: {1}", [
				coupon.code,
				result.message || __("Cart no longer meets requirements"),
			])
		);
	}

	// Re-check a whole-cart coupon for the new customer
	watch(
		() => customer.value?.name || customer.value || null,
		(name, oldName) => {
			const coupon = appliedCoupon.value;
			if (!coupon || isLineLevelCoupon(coupon) || name === oldName) return;
			revalidateWholeCartCoupon(coupon, name);
		}
	);


	// ── Open cart persistence (D-4, INV-2) ──────────────────────────────────────

	/** The cart as a held draft saves it (posDrafts.saveDraftInvoice), plus what a draft does not keep. */
	function buildOpenCartRecord() {
		return {
			pos_profile: posProfile.value,
			customer: customer.value,
			items: invoiceItems.value,
			applied_offers: appliedOffers.value,
			applied_coupon: appliedCoupon.value,
			scope: openCartScope,
			coupon_code: couponCode.value,
			additional_discount: additionalDiscount.value,
			offer_header_discount: offerHeaderDiscount.value,
			fnf_eligibility: fnfEligibility.value,
			fnf_result: fnfResult.value,
			fnf_coupon_override: fnfCouponOverride.value,
			target_doctype: targetDoctype.value,
			// The server-checked draft (Ruling 101). After a reload it is checked before
			// payment (Ruling 136). The check itself (paymentCheck) is not kept (8o).
			payment_draft_name: paymentDraftName.value,
			current_draft_id: currentDraftId.value,
			// The offline sale is queued under this id, so paying the cart again dedups (Ruling 136 (d)).
			offline_id: cartOfflineId.value,
			// F5's online submit key and its state (F6): a cart restored while its submit
			// had no answer re-sends the same key, so the server returns that sale.
			idempotency_key: pendingSubmit.value?.key || null,
			pending_submit: pendingSubmit.value,
			last_online_payment: lastOnlinePayment.value,
			updated_at: new Date().toISOString(),
		};
	}

	/** A cart worth keeping: lines, or a customer other than the profile default. */
	function hasOpenCartContent() {
		if (invoiceItems.value.length > 0) return true;
		if (pendingSubmit.value?.unresolved) return true; // a cleared key is kept (Ruling 146 (d))
		const name = currentCustomerName();
		return Boolean(name) && name !== (defaultCustomerName.value || null);
	}

	function cancelOpenCartSave() {
		if (openCartTimer) clearTimeout(openCartTimer);
		openCartTimer = null;
	}

	// The snapshot is taken when the save runs, not when it was scheduled.
	function saveOpenCart() {
		openCartTimer = null;
		if (!openCartScope || openCartSuspended) return Promise.resolve(false);
		if (!hasOpenCartContent()) return deleteOpenCart();
		return writeOpenCart(buildOpenCartRecord());
	}

	function scheduleOpenCartSave() {
		if (!openCartScope || openCartSuspended) return;
		cancelOpenCartSave();
		openCartTimer = setTimeout(saveOpenCart, OPEN_CART_SAVE_DELAY_MS);
	}

	/** Save now, skipping the debounce (before an offline queue write). */
	function flushOpenCartSave() {
		cancelOpenCartSave();
		return saveOpenCart();
	}
	// The submit key is saved before its request goes out (F6).
	setBeforeSubmitRequest(flushOpenCartSave);

	/**
	 * The offline_id this cart's offline sale is queued under. Made once per cart and
	 * saved at once, so a crash after the queue write still restores it (Ruling 136 (d)).
	 */
	async function checkoutOfflineId() {
		if (!cartOfflineId.value) cartOfflineId.value = generateOfflineId();
		await flushOpenCartSave();
		return cartOfflineId.value;
	}

	function stopWaitingForOnline() {
		if (stopRepriceWhenOnline) stopRepriceWhenOnline();
		stopRepriceWhenOnline = null;
	}

	/** Why payment is blocked: a restored draft not yet checked on the server (Ruling 136 (b)). */
	const paymentBlockedMessage = computed(() =>
		unverifiedDraftName.value
			? __("Invoice {0} may already be paid. Go online to check it before taking payment.", [
					unverifiedDraftName.value,
				])
			: ""
	);

	/** The draft was submitted after all: close the cart as sold, never sell it again. */
	function closeAsAlreadySubmitted(row) {
		unverifiedDraftName.value = null;
		// Its sale is known: no key is left to ask about (no second notice for it).
		dropPendingSubmit();
		clearCart({ returnSerials: false });
		alreadySubmittedInvoice.value = {
			name: row.name,
			grand_total: Number(row.grand_total) || 0,
			rounded_total: Number(row.rounded_total) || 0,
			paid_amount: Number(row.paid_amount) || 0,
		};
	}

	/**
	 * Ask the server what the cart's payment draft became (Ruling 136 (a)):
	 * "submitted" (the cart is closed as sold), "draft" (still open, reused),
	 * "gone" (cleaned up or cancelled: a new draft is safe) or "unverified" (offline,
	 * or the check failed: payment stays blocked).
	 */
	async function verifyPaymentDraft() {
		const name = unverifiedDraftName.value || paymentDraftName.value;
		if (!name) return "gone";
		unverifiedDraftName.value = name;
		if (offlineState.isOffline) return "unverified";
		let row;
		try {
			row = await call("frappe.client.get_value", {
				doctype: "Sales Invoice",
				filters: { name },
				fieldname: ["name", "docstatus", "grand_total", "rounded_total", "paid_amount"],
			});
		} catch (error) {
			console.error("Could not check the payment draft:", error);
			return "unverified";
		}
		if (unverifiedDraftName.value !== name) return "gone"; // the cart was cleared meanwhile
		if (row?.name && Number(row.docstatus) === 1) {
			closeAsAlreadySubmitted(row);
			return "submitted";
		}
		unverifiedDraftName.value = null;
		if (row?.name && Number(row.docstatus) === 0) return "draft";
		if (paymentDraftName.value === name) paymentDraftName.value = null;
		return "gone";
	}

	/**
	 * Before payment opens: a restored draft must be checked first. Resolves
	 * { allowed, message }; a submitted draft closes the cart (alreadySubmittedInvoice).
	 */
	async function ensurePaymentAllowed() {
		if (!unverifiedDraftName.value) return { allowed: true, message: "" };
		const status = await verifyPaymentDraft();
		if (status === "draft" || status === "gone") return { allowed: true, message: "" };
		if (status === "submitted") return { allowed: false, message: "", alreadySubmitted: true };
		if (offlineState.isOffline) return { allowed: false, message: paymentBlockedMessage.value };
		return {
			allowed: false,
			message: __("Could not check invoice {0}. Try again before taking payment.", [unverifiedDraftName.value]),
		};
	}

	/**
	 * Re-price a restored cart as after a customer or qty change: F&F eligibility is
	 * asked again, the coupon re-checked and the offers (with F&F) re-evaluated.
	 * A restored payment draft is checked first. Offline, the cart stays as it was
	 * saved until the POS is back online.
	 */
	async function repriceRestoredCart() {
		stopWaitingForOnline();
		if (offlineState.isOffline) {
			stopRepriceWhenOnline = offlineState.subscribe(() => {
				if (offlineState.isOffline) return;
				repriceRestoredCart();
			});
			return;
		}
		if (unverifiedDraftName.value && (await verifyPaymentDraft()) === "submitted") return;
		await Promise.all([
			syncOneTimeContextForCurrentCustomer(),
			refreshFriendsAndFamilyEligibility(true),
		]).catch(() => {});
		if (invoiceItems.value.length === 0) return;
		const coupon = appliedCoupon.value;
		if (isWholeCartCoupon(coupon)) revalidateWholeCartCoupon(coupon, currentCustomerName());
		else if (isLineLevelCoupon(coupon)) scheduleCouponRevalidation();
		forceRefreshOffers();
	}

	function applyOpenCartRecord(record) {
		debouncedProcessOffers.cancel();
		offerQueue.cancel();
		paymentCheck.value = null;

		// Lines first: the coupon below must find them.
		invoiceItems.value = Array.isArray(record.items) ? record.items : [];
		rebuildIncrementalCache();
		if (record.customer) customer.value = record.customer;
		appliedOffers.value = Array.isArray(record.applied_offers) ? record.applied_offers : [];
		offerHeaderDiscount.value = Number(record.offer_header_discount) || 0;
		additionalDiscount.value = Number(record.additional_discount) || 0;
		// Offline, the badge keeps the saved answer (same customer); online it is asked again.
		fnfEligibility.value = record.fnf_eligibility || null;
		fnfEligibilityKey = null;
		fnfResult.value = record.fnf_result || null;
		fnfCouponOverride.value = record.fnf_coupon_override || null;
		targetDoctype.value = settingsStore.createOnlySalesOrder
			? "Sales Order"
			: record.target_doctype || "Sales Invoice";
		paymentDraftName.value = record.payment_draft_name || null;
		// Possibly submitted before the reload: payment waits for the server's answer.
		unverifiedDraftName.value = paymentDraftName.value;
		currentDraftId.value = record.current_draft_id || null;
		cartOfflineId.value = record.offline_id || null;
		pendingSubmit.value = record.pending_submit?.key ? record.pending_submit : null;
		lastOnlinePayment.value = record.last_online_payment || null;

		const coupon = record.applied_coupon || null;
		if (isWholeCartCoupon(coupon)) {
			appliedCoupon.value = coupon;
			couponCode.value = record.coupon_code || coupon.code || coupon.name || null;
		} else {
			// A scoped coupon goes back on its lines; without one, no coupon line survives.
			restoreLineCoupon(coupon);
		}
		rebuildIncrementalCache();
		offerProcessingState.value.lastCartHash = "";
		syncOfferSnapshot();
	}

	/**
	 * After a reload: bring back this tab's cart saved for this user, POS Profile and
	 * opening shift, and save the cart from now on. A cart saved for any other scope is
	 * deleted, never shown. Online, a restored payment draft that was already submitted
	 * closes the cart (alreadySubmittedInvoice). Returns true when a cart was restored.
	 * @param {{ user: string, pos_profile: string, pos_opening_shift: string }} scope
	 */
	async function restoreOpenCart(scope) {
		cancelOpenCartSave();
		stopWaitingForOnline();
		openCartScope = null; // nothing is saved before the saved cart is read
		openCartSuspended = false;
		const key = openCartScopeKey(scope);
		if (!key) return false;

		const record = await readOpenCart();
		// Other tabs' carts for another user, POS Profile or shift can never be restored.
		await deleteOpenCarts(key);
		openCartScope = {
			user: scope.user,
			pos_profile: scope.pos_profile,
			pos_opening_shift: scope.pos_opening_shift,
		};
		if (!record) return false;
		const hasLines = Array.isArray(record.items) && record.items.length > 0;
		if (openCartScopeKey(record.scope) === key && !hasLines && record.pending_submit?.unresolved && record.pending_submit.key) {
			// Only a cleared, unanswered submit's key was kept (Ruling 146 (d)): no cart.
			pendingSubmit.value = record.pending_submit;
			return false;
		}
		if (openCartScopeKey(record.scope) !== key || (!hasLines && !record.customer)) {
			await deleteOpenCart();
			return false;
		}
		try {
			applyOpenCartRecord(record);
		} catch (error) {
			console.error("Could not restore the open cart:", error);
			clearCart();
			return false;
		}
		// Its offline sale was queued before the crash: paying it again, online, would be
		// a second sale beside the queued one (F6, F4 m2).
		const offlineId = cartOfflineId.value;
		if (offlineId && (await findQueuedSale(offlineId))) {
			dropPendingSubmit();
			clearCart({ returnSerials: false });
			alreadyQueuedSale.value = { offline_id: offlineId };
			return false;
		}
		if (unverifiedDraftName.value && !offlineState.isOffline) {
			// Checked before the cart is shown: a sold cart never comes back.
			if ((await verifyPaymentDraft()) === "submitted") return false;
		}
		// A submit of this cart got no answer: it is re-sent as it was. A re-price could
		// change its rows, and so its key: a second sale (F6).
		if (!hasUnresolvedSubmit()) repriceRestoredCart();
		return true;
	}

	/** The shift closed: drop the cart and every tab's saved copy; nothing is saved until the next restoreOpenCart(). */
	async function stopCartPersistence() {
		clearCart();
		cancelOpenCartSave();
		stopWaitingForOnline();
		openCartScope = null;
		await deleteOpenCarts();
	}

	/**
	 * A cart loaded to edit an offline invoice is not saved: restored without its edit
	 * context, paying it would queue a second invoice. The next clearCart() resumes saving.
	 */
	async function suspendCartPersistence() {
		cancelOpenCartSave();
		openCartSuspended = true;
		await deleteOpenCart();
	}

	watch(
		[
			invoiceItems,
			customer,
			appliedOffers,
			appliedCoupon,
			additionalDiscount,
			fnfEligibility,
			fnfResult,
			fnfCouponOverride,
			targetDoctype,
			paymentDraftName,
			currentDraftId,
			cartOfflineId,
			pendingSubmit,
			lastOnlinePayment,
		],
		scheduleOpenCartSave,
		{ deep: true }
	);

	// Additional watcher for applied offers changes (to handle removal edge cases)
	watch(
		() => appliedOffers.value.length,
		(newLen, oldLen) => {
			// If offers were removed externally, sync the snapshot
			if (newLen < oldLen) {
				syncOfferSnapshot();
			}
		}
	);

	return {
		// State
		invoiceItems,
		customer,
		subtotal,
		totalTax,
		lineTotalTax, // tax before the header discount (D-R2-07): for arithmetic, not the Tax row
		totalDiscount,
		grandTotal,
		posProfile,
		posOpeningShift,
		payments,
		salesTeam,
		additionalDiscount,
		couponCode,
		taxInclusive,
		pendingItem,
		pendingItemQty,
		appliedOffers,
		appliedCoupon,
		selectionMode,
		currentDraftId,
		offerProcessingState, // Offer processing state for UI feedback
		fnfEligibility, // PN-130: F&F eligibility of the current customer
		fnfResult, // PN-130: last server F&F decision for the cart
		fnfCouponOverride, // PN-130: coupon that replaced F&F, if any
		paymentDraftName, // the server-checked unpaid draft (Ruling 101)
		alreadySubmittedInvoice, // set when a restored cart turned out sold (Ruling 136 (a))
		alreadyQueuedSale, // set when a restored cart's offline sale was already queued (F6)
		madeSaleNotice, // the sale a cleared, unanswered submit made (Ruling 144)
		dismissMadeSaleNotice,
		submitDecision, // "is this the same sale?" while the cashier is asked (Ruling 146)
		decideSubmit,
		settlePendingSubmit,
		pendingMatchesCart,
		pendingSubmit,
		closeAsAlreadySubmitted,
		paymentBlockedMessage, // non-empty while a restored draft is unchecked (Ruling 136 (b))
		lastOnlinePayment, // saved with the cart (F6)

		// Computed
		itemCount,
		isEmpty,
		hasCustomer,
		isProcessingOffers, // True when any offer operation is in progress
		isSubmitting, // True when invoice submission is in progress (mutex protected)

		// Actions
		addItem,
		removeItem,
		updateItemQuantity,
		clearCart,
		setCustomer,
		setDefaultCustomer: loadDefaultCustomer,
		setPendingItem,
		clearPendingItem,
		loadTaxRules,
		setTaxInclusive,
		submitInvoice,
		hasUnresolvedSubmit,
		releaseSubmitKey,
		resolvePendingSubmit: resolvePendingSubmitAndTell,
		dropPendingSubmit,
		checkPriceBeforePayment,
		paymentTotal,
		paymentRoundingAdjustment,
		roundedTotal,
		roundingAdjustment,
		applyDiscountToCart,
		removeDiscountFromCart,
		dropRefusedCoupon,
		buildCouponItemsPayload,
		restoreLineCoupon,
		applyOffer,
		removeOffer,
		reapplyOffer,
		changeItemUOM,
		updateItemDetails,
		getItemDetailsResource,
		resolveUomPricing,
		recalculateItem,
		rebuildIncrementalCache,
		applyOffersResource,
		buildOfferEvaluationPayload,
		formatItemsForSubmission,

		// Sales Order feature
		targetDoctype,
		setTargetDoctype,
		evaluateFriendsAndFamilyOnly,
		createSalesOrder,
		deliveryDate,
		setDeliveryDate,

		// Write-off feature
		writeOffAmount,
		setWriteOffAmount,

		// Utilities
		cancelPendingOfferProcessing: () => {
			debouncedProcessOffers.cancel();
			offerQueue.cancel();
		},
		forceRefreshOffers, // Force reprocess offers from scratch
		refreshFriendsAndFamilyEligibility,
		recheckFriendsAndFamily,

		// Open cart persistence (D-4)
		restoreOpenCart,
		stopCartPersistence,
		suspendCartPersistence,
		ensurePaymentAllowed,
		checkoutOfflineId,
	};
});
