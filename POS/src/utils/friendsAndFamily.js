/**
 * Friends & Family (F&F) helpers for the POS cart — PN-130.
 *
 * The program lives in the optional POSNext Promotions app. The server owns
 * every F&F decision (rate from Settings, coverage, best-discount comparison,
 * caps); this module only reads its payloads and turns them into what the
 * cashier sees: line stamps, badges, price breakdowns and messages.
 *
 * Payload contract (posnext_promotions):
 *   - check_friends_and_family_eligibility(customer)
 *       → { eligible, reason, message, discount_percentage, program: { user_message, … } }
 *   - apply_offers(...)  → { items, friends_and_family: {…}, best_discount: {…} }
 *   - apply_friends_and_family_discount(customer, items)
 *       → same shape as the `friends_and_family` block, plus best_discount
 *   F&F line results carry `idx` (cart index), `applies`, `discount_amount`
 *   (line total), `rate` (net unit), `reason`, `capped`, `best_discount`.
 *
 * Pure functions only (no stores, no network) so they are unit-testable.
 */

export const FNF_DISCOUNT_SOURCE = "friends_and_family";

export const FNF_REASON = Object.freeze({
	APPLIED: "applied",
	OUT_OF_SCOPE: "out_of_scope",
	EXCLUDED: "excluded",
	NO_COVERED_ITEMS: "no_covered_items",
	OTHER_BETTER: "other_discount_better",
	PROTECTED: "protected_line",
	NOT_DISCOUNTABLE: "not_discountable",
	INELIGIBLE: "customer_ineligible",
	PROGRAM_INACTIVE: "program_inactive",
	STRIPPED: "stripped",
	ORDER_DISCOUNT_BETTER: "order_discount_better",
	CAP_REACHED: "cap_reached",
});

export const COUPON_REASON_BETTER_DISCOUNT_EXISTS = "better_discount_exists";

/** Line discount sources shown to the cashier (mirrors best_discount.classify_line_source). */
export const LINE_SOURCE = Object.freeze({
	FRIENDS_AND_FAMILY: "friends_and_family",
	PROMOTION: "promotion",
	COUPON: "coupon",
	MANUAL: "manual",
	FREE: "free",
	NONE: "none",
});

const PROMOTION_DISCOUNT_SOURCES = new Set([
	"auto_discount",
	"item_level_promotion",
	"accumulative_promotion",
	"pricing_rule",
]);
const FREE_DISCOUNT_SOURCES = new Set(["gwp", "free_item"]);

/** Client-only fields stamped on cart items by the F&F integration. */
export const FNF_ITEM_FIELDS = Object.freeze([
	"fnf_reason",
	"fnf_capped",
	"fnf_discount_amount",
	"fnf_qty",
	"fnf_rate",
	"fnf_uncapped_amount",
	"fnf_competing_source",
	"fnf_competing_amount",
	"fnf_decision",
]);

function t(text, args) {
	const translate = globalThis.__;
	if (typeof translate === "function") return translate(text, args);
	if (!args) return text;
	return text.replace(/{(\d+)}/g, (match, n) => (args[n] !== undefined ? args[n] : match));
}

function num(value) {
	const parsed = Number.parseFloat(value);
	return Number.isFinite(parsed) ? parsed : 0;
}

function round2(value) {
	return Math.round((num(value) + Number.EPSILON) * 100) / 100;
}

function hasPricingRules(value) {
	if (!value) return false;
	if (Array.isArray(value)) return value.some(Boolean);
	return typeof value === "string" && value.replace(/[[\]"\s,]/g, "").length > 0;
}

/** True when the cart line currently carries a Friends & Family stamp. */
export function isFnfLine(item) {
	return Boolean(item) && item.discount_source === FNF_DISCOUNT_SOURCE;
}

/** Arabic UI → `message_ar`; English → `message_en`; anything else → server-translated `message`. */
export function pickLocalizedMessage(payload, locale = "en") {
	if (!payload || typeof payload !== "object") return "";
	const lang = String(locale || "en").toLowerCase();
	if (lang.startsWith("ar")) return payload.message_ar || payload.message || payload.message_en || "";
	if (lang.startsWith("en")) return payload.message_en || payload.message || "";
	return payload.message || payload.message_en || "";
}

/** Normalize check_friends_and_family_eligibility() for the store. */
export function normalizeEligibility(response, customer = null) {
	const payload = response?.message && typeof response.message === "object" ? response.message : response;
	if (!payload || typeof payload !== "object") return null;
	const eligible = Boolean(payload.eligible);
	return {
		customer: payload.customer || customer || null,
		eligible,
		reason: payload.reason || "",
		message: payload.message || "",
		discountPercentage: eligible ? num(payload.discount_percentage) : 0,
		// Admin-editable template from Friends and Family Settings.
		userMessage: (eligible && (payload.program?.user_message || payload.message)) || "",
		program: eligible ? payload.program || null : null,
	};
}

/**
 * Normalize an F&F result: the `friends_and_family` block of apply_offers or
 * the apply_friends_and_family_discount() response. Returns null when the
 * server sent no F&F block (customer ineligible / program off on that path).
 */
export function normalizeFnfResult(block, bestDiscount = null) {
	const payload = block?.message && typeof block.message === "object" ? block.message : block;
	if (!payload || typeof payload !== "object") return null;
	const caps = payload.caps && typeof payload.caps === "object" ? payload.caps : null;
	return {
		eligible: Boolean(payload.eligible),
		discountPercentage: num(payload.discount_percentage),
		appliedCount: Number.parseInt(payload.applied_count, 10) || 0,
		reason: payload.reason || "",
		message: payload.message || "",
		message_en: payload.message_en || "",
		message_ar: payload.message_ar || "",
		userMessage: payload.user_message || "",
		lines: Array.isArray(payload.items) ? payload.items : [],
		caps,
		capHit: payload.cap_hit || caps?.cap_hit || null,
		bestDiscount: bestDiscount || payload.best_discount || null,
	};
}

/** Map cart index → F&F line result. */
export function indexFnfLines(result) {
	const map = new Map();
	for (const line of result?.lines || []) {
		const idx = Number.parseInt(line?.idx, 10);
		if (Number.isInteger(idx)) map.set(idx, line);
	}
	return map;
}

/** Copy the server's per-line F&F decision onto the cart item (informational fields only). */
export function annotateFnfLine(item, line) {
	if (!item) return;
	if (!line) {
		clearFnfAnnotations(item);
		return;
	}
	item.fnf_reason = line.reason || "";
	item.fnf_capped = Boolean(line.capped);
	item.fnf_uncapped_amount = num(line.fnf_uncapped_amount);
	item.fnf_competing_source = line.competing_source || null;
	item.fnf_competing_amount = num(line.competing_amount);
	item.fnf_decision = line.best_discount || null;
}

export function clearFnfAnnotations(item) {
	if (!item) return;
	item.fnf_reason = "";
	item.fnf_capped = false;
	item.fnf_uncapped_amount = 0;
	item.fnf_competing_source = null;
	item.fnf_competing_amount = 0;
	item.fnf_decision = null;
}

/**
 * Stamp the server's F&F discount on a cart item.
 *
 * Uses the server `discount_amount` (line total) as the source of truth: on a
 * capped line `discount_percentage` is unrounded, so recomputing from % would
 * drift by a cent. `fnf_qty` pins the amount to the quantity it was computed
 * for; recalculateItem falls back to the % if the qty changes before the
 * next server round-trip.
 */
export function stampFnfLine(item, line) {
	if (!item || !line) return;
	const qty = num(item.quantity ?? item.qty);
	item.discount_percentage = num(line.discount_percentage);
	item.discount_amount = num(line.discount_amount);
	item.discount_source = FNF_DISCOUNT_SOURCE;
	item.pricing_rules = [];
	item.is_already_discounted = 1;
	item.is_accumulative_discount = 0;
	item.fnf_discount_amount = num(line.discount_amount);
	item.fnf_qty = qty;
	item.fnf_rate = num(line.rate);
	annotateFnfLine(item, line);
}

/** Remove an F&F stamp (ineligible customer, coupon won, program ended…). */
export function stripFnfLine(item) {
	if (!item) return false;
	const wasFnf = isFnfLine(item);
	if (wasFnf) {
		item.discount_percentage = 0;
		item.discount_amount = 0;
		item.discount_source = "";
		item.is_already_discounted = 0;
	}
	item.fnf_discount_amount = 0;
	item.fnf_qty = 0;
	item.fnf_rate = 0;
	return wasFnf;
}

function normalizePricingRules(value) {
	if (Array.isArray(value)) return [...value];
	if (typeof value === "string" && value.trim()) {
		return value
			.split(",")
			.map((part) => part.trim())
			.filter(Boolean);
	}
	return [];
}

/**
 * Merge one apply_offers response line into its cart item (PN-130).
 *
 * - F&F applies (per the F&F block) and no coupon replaced it → stamp F&F.
 * - Server applied another discount / pricing rule → take it, dropping any
 *   old F&F stamp.
 * - Server returned nothing for a line that still carries F&F → strip it.
 *   This is the "ineligible customer" case: apply_offers then echoes the
 *   request lines back unchanged, so an F&F % in `serverItem` is ignored.
 * - Otherwise a manual cashier discount is preserved (pre-PN-130 behaviour).
 *
 * Mutates `item`; the caller recalculates totals.
 * @returns {{discounted: boolean, stamped: boolean, stripped: boolean}}
 */
export function mergeServerLine(item, serverLine = {}, fnfLine = null, { fnfSuppressed = false } = {}) {
	const result = { discounted: false, stamped: false, stripped: false };
	if (!item) return result;
	const serverItem = serverLine || {};

	if (fnfLine?.applies && !fnfSuppressed && !item.is_free_item) {
		stampFnfLine(item, fnfLine);
		item.free_qty = num(serverItem.free_qty);
		item.gwp_free_qty = num(serverItem.gwp_free_qty);
		result.discounted = true;
		result.stamped = true;
		return result;
	}
	annotateFnfLine(item, fnfLine || null);

	const serverIsFnf = serverItem.discount_source === FNF_DISCOUNT_SOURCE;
	const discountPct = serverIsFnf ? 0 : num(serverItem.discount_percentage);
	const discountAmt = serverIsFnf ? 0 : num(serverItem.discount_amount);
	const serverRules = serverIsFnf ? [] : normalizePricingRules(serverItem.pricing_rules);

	if (serverRules.length > 0 || discountPct > 0 || discountAmt > 0) {
		const wasFnf = stripFnfLine(item);
		item.discount_percentage = discountPct;
		item.discount_amount = discountAmt;
		item.pricing_rules = serverRules;
		item.discount_source = serverItem.discount_source || (wasFnf ? "" : item.discount_source);
		item.free_qty = num(serverItem.free_qty);
		item.gwp_free_qty = num(serverItem.gwp_free_qty);
		result.discounted = discountPct > 0 || discountAmt > 0;
	} else if (isFnfLine(item)) {
		stripFnfLine(item);
		item.pricing_rules = [];
		result.stripped = true;
	}

	if (result.stripped) {
		item.is_already_discounted = 0; // the echoed request flag is stale
	} else if (serverItem.is_already_discounted !== undefined) {
		item.is_already_discounted = serverItem.is_already_discounted ? 1 : 0;
	}
	item.is_accumulative_discount = serverItem.discount_source === "accumulative_promotion" ? 1 : 0;
	return result;
}

/**
 * Exact F&F line discount for recalculateItem, or null to fall back to the
 * normal % / amount maths (qty changed since the server priced the line).
 */
export function fnfLockedDiscountAmount(item, baseAmount) {
	if (!isFnfLine(item)) return null;
	const amount = num(item.fnf_discount_amount);
	if (amount <= 0) return null;
	if (num(item.fnf_qty) !== num(item.quantity ?? item.qty)) return null;
	return Math.min(round2(amount), num(baseAmount));
}

/** Which discount the line currently carries (badge / breakdown label). */
export function lineDiscountSource(item) {
	if (!item) return LINE_SOURCE.NONE;
	if (item.is_free_item) return LINE_SOURCE.FREE;
	const source = item.discount_source || "";
	if (source === FNF_DISCOUNT_SOURCE) return LINE_SOURCE.FRIENDS_AND_FAMILY;
	if (FREE_DISCOUNT_SOURCES.has(source) || num(item.free_qty) > 0 || num(item.gwp_free_qty) > 0) {
		return LINE_SOURCE.FREE;
	}
	if (num(item.discount_amount) <= 0 && num(item.discount_percentage) <= 0) return LINE_SOURCE.NONE;
	if (source === "coupon" || item.posnext_coupon_code) return LINE_SOURCE.COUPON;
	if (PROMOTION_DISCOUNT_SOURCES.has(source) || hasPricingRules(item.pricing_rules)) {
		return LINE_SOURCE.PROMOTION;
	}
	return LINE_SOURCE.MANUAL;
}

export function lineSourceLabel(source) {
	switch (source) {
		case LINE_SOURCE.FRIENDS_AND_FAMILY:
			return t("Friends & Family");
		case LINE_SOURCE.PROMOTION:
			return t("Promotion");
		case LINE_SOURCE.COUPON:
			return t("Coupon");
		case LINE_SOURCE.MANUAL:
			return t("Manual discount");
		case LINE_SOURCE.FREE:
			return t("Free item offer");
		default:
			return "";
	}
}

/** Short badge prefix ("F&F", "Promo", "Coupon"); empty for manual / none. */
export function lineSourceShortLabel(source) {
	switch (source) {
		case LINE_SOURCE.FRIENDS_AND_FAMILY:
			return t("F&F");
		case LINE_SOURCE.PROMOTION:
			return t("Promo");
		case LINE_SOURCE.COUPON:
			return t("Coupon");
		default:
			return "";
	}
}

/** Original (list) price, discount and final price of a cart line. */
export function lineBreakdown(item) {
	const qty = num(item?.quantity ?? item?.qty);
	const unit = num(item?.price_list_rate || item?.rate);
	const original = round2(qty * unit);
	const discount = Math.min(round2(item?.discount_amount), original);
	return {
		source: lineDiscountSource(item),
		original,
		discount,
		final: round2(original - discount),
	};
}

/** Sum of line discounts per source, for the totals breakdown. */
export function discountTotalsBySource(items) {
	const totals = {
		[LINE_SOURCE.FRIENDS_AND_FAMILY]: 0,
		[LINE_SOURCE.PROMOTION]: 0,
		[LINE_SOURCE.COUPON]: 0,
		[LINE_SOURCE.MANUAL]: 0,
		[LINE_SOURCE.FREE]: 0,
	};
	for (const item of items || []) {
		if (item?.is_free_item) continue;
		const amount = round2(item?.discount_amount);
		if (amount <= 0) continue;
		const source = lineDiscountSource(item);
		if (source in totals) totals[source] = round2(totals[source] + amount);
	}
	return totals;
}

/**
 * Cashier note for a line that is NOT receiving F&F although the customer is
 * eligible (excluded, promo better, cap reached…), or for a capped F&F line.
 */
export function fnfLineNote(item, { locale = "en" } = {}) {
	if (!item) return null;
	if (isFnfLine(item)) {
		if (item.fnf_capped) {
			return { tone: "warning", text: t("Friends & Family reduced by the discount limit") };
		}
		return null;
	}
	switch (item.fnf_reason) {
		case FNF_REASON.EXCLUDED:
			return { tone: "muted", text: t("Excluded from Friends & Family") };
		case FNF_REASON.OUT_OF_SCOPE:
			return { tone: "muted", text: t("Not covered by Friends & Family") };
		case FNF_REASON.CAP_REACHED:
			return { tone: "warning", text: t("Friends & Family limit reached") };
		case FNF_REASON.ORDER_DISCOUNT_BETTER:
			return { tone: "info", text: t("Invoice promotion applied instead of Friends & Family") };
		case FNF_REASON.OTHER_BETTER: {
			const text = pickLocalizedMessage(item.fnf_decision, locale);
			return { tone: "info", text: text || t("A better discount applies instead of Friends & Family") };
		}
		default:
			return null;
	}
}

function fnfAppliedTotal(result) {
	if (result?.caps && result.caps.fnf_applied_total !== undefined) {
		return round2(result.caps.fnf_applied_total);
	}
	return round2(
		(result?.lines || [])
			.filter((line) => line?.applies)
			.reduce((sum, line) => sum + num(line.discount_amount), 0)
	);
}

/**
 * Cart-level cashier messages, in display order.
 *
 * @param {Object} state
 * @param {Object|null} state.result       normalizeFnfResult() of the last evaluation
 * @param {Object|null} state.eligibility  normalizeEligibility() for the customer
 * @param {Object|null} state.couponOverride { code, message, message_en, message_ar } when a coupon beat F&F
 * @param {string} state.locale
 * @param {Function} state.formatAmount
 * @param {boolean} state.hasItems
 * @returns {Array<{key: string, tone: string, text: string}>}
 */
export function buildFnfCartMessages({
	result = null,
	eligibility = null,
	couponOverride = null,
	locale = "en",
	formatAmount = (v) => round2(v).toFixed(2),
	hasItems = true,
} = {}) {
	const messages = [];
	if (!hasItems) return messages;

	if (couponOverride) {
		messages.push({
			key: "coupon",
			tone: "info",
			text:
				pickLocalizedMessage(couponOverride, locale) ||
				t("Coupon {0} applied instead of Friends & Family — discounts are never combined.", [
					couponOverride.code || "",
				]),
		});
		return messages;
	}

	if (!result) return messages;
	const eligible = result.eligible || eligibility?.eligible;
	if (!eligible) return messages;

	const caps = result.caps || {};
	const best = result.bestDiscount || {};
	const pct = result.discountPercentage || eligibility?.discountPercentage || 0;

	if (result.appliedCount > 0) {
		messages.push({
			key: "applied",
			tone: "success",
			text: t("Friends & Family {0}% applied to {1} item(s) — saving {2}", [
				String(Number(pct.toFixed(2))),
				String(result.appliedCount),
				formatAmount(fnfAppliedTotal(result)),
			]),
		});
	}

	if (caps.capped) {
		messages.push({
			key: "cap",
			tone: "warning",
			text: pickLocalizedMessage(caps, locale) || t("Friends & Family discount limited by the program cap"),
		});
	}

	if (result.reason === FNF_REASON.NO_COVERED_ITEMS) {
		messages.push({
			key: "coverage",
			tone: "warning",
			text: t("No Friends & Family discount — every item in the cart is excluded or out of scope."),
		});
	}

	// Comparison headline (PN-128): only when something was actually not applied.
	const suppressed = Array.isArray(best.suppressed) ? best.suppressed : [];
	const orderLost = result.reason === FNF_REASON.ORDER_DISCOUNT_BETTER;
	if (suppressed.length > 0 || orderLost) {
		const text = pickLocalizedMessage(best, locale);
		if (text) messages.push({ key: "comparison", tone: "info", text });
	}

	if (caps.active && caps.monthly_remaining !== null && caps.monthly_remaining !== undefined) {
		const after = caps.monthly_remaining_after;
		messages.push({
			key: "monthly",
			tone: "muted",
			text:
				after !== null && after !== undefined
					? t("Monthly Friends & Family balance: {0} left, {1} after this order", [
							formatAmount(caps.monthly_remaining),
							formatAmount(after),
					  ])
					: t("Monthly Friends & Family balance: {0} left", [formatAmount(caps.monthly_remaining)]),
		});
	}

	return messages;
}
