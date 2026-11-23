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
 *       → { eligible, reason, message, discount_percentage, program: {…}, email_domain, ff_member,
 *           customer_message: { ar, en, message } | null }   ("ff_activated" Friends and Family Message)
 *   - apply_offers(...)  → { items, friends_and_family: {…}, best_discount: {…} }
 *   - apply_friends_and_family_discount(customer, items)
 *       → same shape as the `friends_and_family` block, plus best_discount
 *   F&F line results carry `idx` (cart index), `applies`, `discount_amount`
 *   (line total), `rate` (net unit), `reason`, `capped`, `best_discount`.
 *
 * Pure functions only (no stores, no network) so they are unit-testable.
 */

import { isCouponLine } from "@/utils/couponLines";
import { getPrecision, roundTo } from "@/utils/currency";

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
	// Buy X Get Y / Routine (Item Level Discount) line: not eligible for F&F.
	SCHEME_NOT_ELIGIBLE: "scheme_not_eligible",
	// POS Profile has "Allow F&F" unticked: F&F is off for the whole profile.
	PROFILE_NOT_ALLOWED: "profile_not_allowed",
	// Approved Domains (eligibility): the member's email is not on an approved
	// company domain, or is not OTP-verified / changed since verification.
	EMAIL_DOMAIN_NOT_APPROVED: "email_domain_not_approved",
	EMAIL_NOT_VERIFIED: "email_not_verified",
	// F&F is on but no enabled Approved Domain is configured: nobody gets F&F.
	NO_APPROVED_DOMAINS: "no_approved_domains",
});

/** Eligibility reasons where the customer is an F&F member but their email blocks the discount. */
export const FNF_EMAIL_REASONS = Object.freeze([
	FNF_REASON.EMAIL_DOMAIN_NOT_APPROVED,
	FNF_REASON.EMAIL_NOT_VERIFIED,
	FNF_REASON.NO_APPROVED_DOMAINS,
]);

/**
 * Eligibility reasons that come from the program's settings, not from the customer
 * (D-R2-03). They can change at any time, so they are never kept per customer.
 */
export const FNF_SETTINGS_REASONS = Object.freeze([
	FNF_REASON.PROGRAM_INACTIVE,
	FNF_REASON.NO_APPROVED_DOMAINS,
	FNF_REASON.PROFILE_NOT_ALLOWED,
]);

/** True when a normalizeEligibility() answer depends on the F&F Settings only. */
export function isSettingsEligibility(eligibility) {
	return Boolean(eligibility) && !eligibility.eligible && FNF_SETTINGS_REASONS.includes(eligibility.reason);
}

/**
 * Cashier note when an F&F member is blocked by the Approved Domains email rule,
 * else "". Uses the server's translated message, with a local fallback.
 */
export function fnfEmailBlockMessage(eligibility) {
	if (!eligibility || eligibility.eligible) return "";
	if (!FNF_EMAIL_REASONS.includes(eligibility.reason)) return "";
	if (eligibility.message) return eligibility.message;
	if (eligibility.reason === FNF_REASON.NO_APPROVED_DOMAINS) {
		return t("Friends & Family has no approved email domains configured");
	}
	return eligibility.reason === FNF_REASON.EMAIL_NOT_VERIFIED
		? t("No Friends & Family: verify the customer's email (OTP) first")
		: t("No Friends & Family: the customer needs an email on an approved company domain");
}

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
/** Sales Invoice Item field: the signed snapshot of the discount F&F replaced. */
export const FNF_REPLACED_FIELD = "posnext_fnf_replaced_discount";

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

/**
 * POS Profile "Allow F&F" (`allow_friends_family`, default ticked). Anything but
 * an explicit 0 / false means allowed, so a profile payload from a site that has
 * not installed the field yet (or no profile at all) keeps F&F working. The
 * server enforces the same rule; this only avoids pointless round trips and
 * hides stale badges.
 */
export function isFnfAllowedForProfile(profile) {
	if (!profile || typeof profile !== "object") return true;
	const value = profile.allow_friends_family;
	if (value === undefined || value === null || value === "") return true;
	return !(value === false || value === "0" || Number(value) === 0);
}

/** Arabic UI → `message_ar`; English → `message_en`; anything else → server-translated `message`. */
export function pickLocalizedMessage(payload, locale = "en") {
	if (!payload || typeof payload !== "object") return "";
	const lang = String(locale || "en").toLowerCase();
	if (lang.startsWith("ar")) return payload.message_ar || payload.message || payload.message_en || "";
	if (lang.startsWith("en")) return payload.message_en || payload.message || "";
	return payload.message || payload.message_en || "";
}

/** Server `{ ar, en, message }` customer text → `{ message, message_ar, message_en }`, or null when empty. */
export function normalizeCustomerMessage(customerMessage) {
	if (!customerMessage || typeof customerMessage !== "object") return null;
	const normalized = {
		message: customerMessage.message || "",
		message_ar: customerMessage.ar || customerMessage.message_ar || "",
		message_en: customerMessage.en || customerMessage.message_en || "",
	};
	return normalized.message || normalized.message_ar || normalized.message_en ? normalized : null;
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
		// Matches the F&F Group / Flag rule (also when the email rule failed).
		ffMember: Boolean(payload.ff_member),
		// "ff_activated" Friends and Family Message, shaped for pickLocalizedMessage().
		customerMessage: eligible ? normalizeCustomerMessage(payload.customer_message) : null,
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
export function stampFnfLine(item, line, { precision = getPrecision().currency ?? 2 } = {}) {
	if (!item || !line) return;
	const qty = num(item.quantity ?? item.qty);
	let percentage = num(line.discount_percentage);
	let amount = num(line.discount_amount);
	let rate = num(line.rate);
	const priceListRate = num(item.price_list_rate || item.rate);
	if (line.capped && qty > 0 && priceListRate > 0) {
		// The invoice keeps the server's per-unit rate (D-7), so the cart uses it too.
		const netRate = line.rate === undefined || line.rate === null || line.rate === "" ? null : num(line.rate);
		({ percentage, amount, rate } = cappedUnitValues(priceListRate, qty, amount, precision, netRate));
	}
	item.discount_percentage = percentage;
	item.discount_amount = amount;
	item.discount_source = FNF_DISCOUNT_SOURCE;
	item.pricing_rules = [];
	item.is_already_discounted = 1;
	item.is_accumulative_discount = 0;
	item.fnf_discount_amount = amount;
	item.fnf_qty = qty;
	item.fnf_rate = rate;
	item[FNF_REPLACED_FIELD] = line[FNF_REPLACED_FIELD] || null;
	annotateFnfLine(item, line);
}

// posnext_promotions ff_money._EPSILON
const MONEY_EPSILON = 1e-6;

/**
 * A capped F&F line as a saved invoice row holds it: posnext_promotions
 * `_capped_line_values(..., AMOUNT_BASIS_UNIT)`. The net unit rate is rounded UP to
 * the currency unit (the line never saves more than its allowance), so a cap of
 * 50 on 3 × 100 is 83.34 a unit: 250.02, saving 49.98.
 *
 * - The price is taken at currency precision first, as the invoice row sends it
 *   (a UOM change leaves 10/3 unrounded; the server prices 3.33).
 * - `netRate` is the payload's `rate`. The line-basis cart payload's rate is
 *   `price − allocation / qty`, the very expression the server rounds up for the
 *   unit basis; the unit-basis invoice payload's rate is already rounded. Ceiling it
 *   gives the same rate from both, and stamping the result again gives it back
 *   (re-deriving from the saving does not: 2.5 × 10, saving 0.32 → 0.30).
 *   Without a rate, it is derived from `lineAmount`.
 * - Saving per unit and per line use the system rounding (banker's: 0.325 → 0.32).
 */
export function cappedUnitValues(priceListRate, qty, lineAmount, precision = 2, netRate = null) {
	const plr = roundTo(num(priceListRate), precision);
	const q = num(qty);
	const gross = plr * q;
	if (gross <= 0 || q <= 0) return { percentage: 0, amount: 0, rate: plr };
	const scale = 10 ** precision;
	const raw =
		netRate === null || !Number.isFinite(netRate)
			? plr - Math.max(0, Math.min(num(lineAmount), gross)) / q
			: netRate;
	let rate = Math.ceil(raw * scale - MONEY_EPSILON) / scale;
	rate = Math.min(plr, Math.max(0, rate));
	const perUnit = roundTo(plr - rate, precision);
	const amount = roundTo(perUnit * q, precision);
	return { percentage: (amount / gross) * 100, amount, rate };
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
	item[FNF_REPLACED_FIELD] = null;
	return wasFnf;
}

/**
 * The server-signed snapshot of the discount F&F displaced on this line, as the
 * coupon resolver must see it, else {}. Sent with a line whose pre-coupon state is
 * F&F, so an "Add on top" coupon can stack on that discount (G5). The server verifies
 * the signature; the cart never reads or builds it.
 */
export function fnfReplacedDiscount(item, preDiscountSource) {
	const snapshot = item?.[FNF_REPLACED_FIELD];
	return preDiscountSource === FNF_DISCOUNT_SOURCE && snapshot ? { [FNF_REPLACED_FIELD]: snapshot } : {};
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
		result.discounted = discountPct > 0 || discountAmt > 0;
	} else if (isFnfLine(item)) {
		stripFnfLine(item);
		item.pricing_rules = [];
		result.stripped = true;
	} else if (!item.is_free_item && hasPricingRules(item.pricing_rules)) {
		// The server is the authority for promotion discounts. A line whose
		// promotion (pricing_rules) the server no longer applies must drop it,
		// otherwise the client keeps a stale % and computes min_amt on a
		// different total than the server just used (offers-loop fix, develop).
		item.discount_percentage = 0;
		item.discount_amount = 0;
		item.pricing_rules = [];
		item.is_already_discounted = 0;
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
	if (FREE_DISCOUNT_SOURCES.has(source) || num(item.free_qty) > 0) {
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
		case FNF_REASON.SCHEME_NOT_ELIGIBLE:
			return { tone: "info", text: t("Promotion item — not eligible for Friends & Family") };
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
 * What the cashier is told about F&F: a LINE coupon that took F&F lines (D-15), and capped lines (I2).
 *
 * A line coupon takes only the lines it wins; F&F stays on the others, so it never
 * sets the cart's `fnfCouponOverride` (which drops F&F from every line). The last
 * F&F evaluation still counts the lines the coupon took, so:
 *   - the coupon took every F&F line → `override` (muted badge, "applied instead of
 *     Friends & Family" message, no line notes), as for an order coupon that beat F&F;
 *   - it took some → `result` counts only the lines that kept F&F: count, saving and
 *     the monthly balance after this order.
 * A capped line (I2) keeps the invoice's per-unit saving (49.98 for a 50.00 cap), so
 * the saving and the balance after this order count the stamped amounts too.
 * Otherwise `result` is returned as it is.
 *
 * @returns {{ override: Object|null, result: Object|null }}
 */
export function lineCouponFnfView({ result = null, items = [], appliedCoupon = null } = {}) {
	const fnfItems = (items || []).filter((item) => isFnfLine(item) && !item.is_free_item);
	const replaced = appliedCoupon?.line_level
		? (items || []).filter(
				(item) => isCouponLine(item) && item.pre_coupon_discount?.discount_source === FNF_DISCOUNT_SOURCE
			)
		: [];
	if (replaced.length && !fnfItems.length) {
		// No server text: the cart says "… applied instead of Friends & Family — discounts
		// are never combined." (plan U-18 b); the coupon dialog shows the comparison.
		return { override: { code: appliedCoupon.code || appliedCoupon.name || "" }, result: null };
	}
	if (!result) return { override: null, result };
	const capped = (result.lines || []).some((line) => line?.applies && line?.capped);
	if (!replaced.length && !capped) return { override: null, result };
	// What the lines save as stamped: a capped line keeps the invoice's per-unit rate
	// (49.98, not the evaluation's 50.00), and a line a coupon took saves nothing by F&F.
	const keptTotal = round2(fnfItems.reduce((sum, item) => sum + num(item.discount_amount), 0));
	const view = { ...result, caps: capsForSaving(result, keptTotal) };
	if (replaced.length) {
		view.appliedCount = fnfItems.length;
		view.lines = (result.lines || []).filter((line) => !replaced.includes(items[Number.parseInt(line?.idx, 10)]));
	}
	return { override: null, result: view };
}

/**
 * J1: an F&F result after the cart took F&F off some of its lines by itself (offline,
 * a same-item Buy X Get Y gift beside an F&F line, box off). The stripped lines no
 * longer apply; the count, the saving and the monthly balance after this order count
 * only the lines that still hold F&F, so the cart summary agrees with its lines.
 *
 * @param {Object|null} result   normalizeFnfResult() of the last evaluation
 * @param {Array} items          cart lines, in the order the result's `idx` refers to
 * @param {Array} stripped       the cart lines F&F was taken off
 * @returns {Object|null}
 */
export function fnfResultWithoutLines(result, items = [], stripped = []) {
	if (!result || !stripped.length) return result;
	const fnfItems = (items || []).filter((item) => isFnfLine(item) && !item.is_free_item);
	const keptTotal = round2(fnfItems.reduce((sum, item) => sum + num(item.discount_amount), 0));
	return {
		...result,
		appliedCount: fnfItems.length,
		lines: (result.lines || []).map((line) =>
			stripped.includes(items[Number.parseInt(line?.idx, 10)])
				? { ...line, applies: false, discount_amount: 0, capped: false, reason: FNF_REASON.SCHEME_NOT_ELIGIBLE }
				: line
		),
		caps: capsForSaving(result, keptTotal),
	};
}

/**
 * A Price "buy one" offer (100% off, or a zero Rate, on a limited number of units of a
 * Min/Max rule): the server classifies it as Buy X Get Y (ff_classifier.is_price_bxgy_rule).
 */
export function isPriceBuyOneOffer(offer) {
	if (!offer || offer.offer === "Give Product") return false;
	if (String(offer.apply_on || "").trim() === "Transaction") return false;
	if (!["Min", "Max"].includes(offer.apply_discount_on_price)) return false;
	if (!(num(offer.min_or_max_discount_qty_limit) > 0)) return false;
	const kind = offer.discount_type || offer.rate_or_discount || "Discount Percentage";
	if (kind === "Discount Percentage") return num(offer.discount_percentage) >= 100 - 0.0001;
	if (kind === "Rate") return num(offer.rate) <= 0;
	return false;
}

/** `result.caps` with `fnf_applied_total` = `saving` and the monthly balance moved by the difference. */
function capsForSaving(result, saving) {
	if (!result.caps) return null;
	const shownTotal = fnfAppliedTotal(result);
	const caps = { ...result.caps, fnf_applied_total: saving };
	if (caps.monthly_remaining_after !== null && caps.monthly_remaining_after !== undefined && shownTotal > 0) {
		// Monthly amounts are in company currency: convert at the rate the server used.
		const rate = (num(caps.monthly_remaining) - num(caps.monthly_remaining_after)) / shownTotal || 1;
		caps.monthly_remaining_after = round2(
			Math.max(0, num(caps.monthly_remaining_after) + (shownTotal - saving) * rate)
		);
	}
	return caps;
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

	const emailBlock = fnfEmailBlockMessage(eligibility);
	if (emailBlock) {
		messages.push({ key: "email", tone: "warning", text: emailBlock });
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
		// A line that lost F&F already says so under itself: not twice (D-R4-06)
		const notedOnALine = (result.lines || []).some(
			(line) => line?.best_discount && pickLocalizedMessage(line.best_discount, locale) === text
		);
		if (text && !notedOnALine) messages.push({ key: "comparison", tone: "info", text });
	}

	if (caps.active && caps.monthly_remaining !== null && caps.monthly_remaining !== undefined) {
		// Only F&F that applies is deducted: none when an order discount won or no line kept it (D-R2-04).
		const deducted = result.appliedCount > 0 && !orderLost;
		const after = deducted ? caps.monthly_remaining_after : null;
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

/**
 * Header (invoice-level) discount the cart should carry after an
 * apply_offers response.
 *
 * apply_offers only reports discounts from transaction-scope Pricing Rules
 * (0 when none fired). A POS Coupon is applied client-side as the header
 * discount, so a 0 from the server must not wipe it — otherwise any cart
 * re-evaluation (e.g. the one triggered when a coupon that beat F&F strips
 * the F&F line stamps) silently drops the coupon while F&F stays removed.
 *
 * @param {number|string} serverAmount  discount_amount from apply_offers
 * @param {object|null} appliedCoupon   the coupon currently applied in the cart
 * @returns {{ amount: number, keepCoupon: boolean }}
 *   keepCoupon=true → re-apply the coupon (amount is then ignored).
 */
export function resolveHeaderDiscount(serverAmount, appliedCoupon = null) {
	const amount = Math.max(num(serverAmount), 0);
	if (appliedCoupon && amount <= 0) return { amount: 0, keepCoupon: true };
	return { amount, keepCoupon: false };
}

/**
 * Sales Invoice Item markers for an F&F cart line, else {}. The promotions
 * server reads them (audit, usage ledger, paid-invoice check, gift policy).
 * Program and % go only when the cart already holds them; amounts are never
 * sent, the server derives them.
 */
export function fnfSubmissionMarkers(item) {
	if (!isFnfLine(item) || item.is_free_item) return {};
	const markers = { posnext_discount_source: FNF_DISCOUNT_SOURCE };
	if (item.posnext_fnf_program) markers.posnext_fnf_program = item.posnext_fnf_program;
	if (num(item.posnext_fnf_percentage) > 0)
		markers.posnext_fnf_percentage = num(item.posnext_fnf_percentage);
	return markers;
}

// Sales Orders carry no F&F (the server strips them too; Phase 3 adds real support).
const FNF_HEADER_PREFIX = "posnext_fnf_";

function isFnfMarked(item) {
	return (
		item?.posnext_discount_source === FNF_DISCOUNT_SOURCE ||
		item?.discount_source === FNF_DISCOUNT_SOURCE
	);
}

/** Drop every `posnext_fnf_*` key from a document / line (mutates, returns it). */
export function stripFnfKeys(doc) {
	if (!doc) return doc;
	for (const key of Object.keys(doc)) {
		if (key.startsWith(FNF_HEADER_PREFIX)) delete doc[key];
	}
	return doc;
}

/**
 * Sales Order payloads: F&F lines go back to list price with no discount and lose
 * their F&F keys; every other line (manual, promotion, coupon) is kept as is.
 * A line is F&F when `posnext_discount_source` (document field) or the cart's
 * `discount_source` is "friends_and_family". Pure: input items are not mutated.
 * @returns {{items: object[], stripped: number}}
 */
export function stripFriendsAndFamilyForOrder(items) {
	let stripped = 0;
	const out = (items || []).map((item) => {
		if (!isFnfMarked(item)) return stripFnfKeys({ ...item });
		stripped += 1;
		const copy = stripFnfKeys({ ...item });
		const listRate = item.price_list_rate ?? item.rate;
		const qty = num(item.quantity ?? item.qty);
		copy.discount_percentage = 0;
		copy.discount_amount = 0;
		copy.rate = listRate;
		if ("amount" in copy) copy.amount = round2(num(listRate) * qty);
		if ("posnext_discount_source" in copy) copy.posnext_discount_source = "";
		if ("discount_source" in copy) copy.discount_source = "";
		if ("is_already_discounted" in copy) copy.is_already_discounted = 0;
		for (const field of FNF_ITEM_FIELDS) delete copy[field];
		return copy;
	});
	return { items: out, stripped };
}

/**
 * D-R2-14: what the payment dialog says when an invoice discount is entered on a cart
 * with F&F lines, else "". The two are never combined; the server keeps the better
 * one when the sale is paid. When F&F already saves at least as much, the invoice
 * discount will not apply.
 */
export function invoiceDiscountFnfConflict({
	items = [],
	invoiceDiscount = 0,
	formatAmount = (v) => round2(v).toFixed(2),
} = {}) {
	const discount = num(invoiceDiscount);
	const fnfSaving = round2(
		(items || [])
			.filter((item) => isFnfLine(item) && !item.is_free_item)
			.reduce((sum, item) => sum + num(item.discount_amount), 0)
	);
	if (discount <= 0 || fnfSaving <= 0) return "";
	if (fnfSaving >= discount) {
		return t(
			"Friends & Family ({0}) is better than this invoice discount ({1}). They are never combined: the invoice discount will not be applied when you pay.",
			[formatAmount(fnfSaving), formatAmount(discount)]
		);
	}
	return t(
		"Friends & Family ({0}) and this invoice discount ({1}) are never combined: when you pay, the better of the two is kept and the total may change.",
		[formatAmount(fnfSaving), formatAmount(discount)]
	);
}
