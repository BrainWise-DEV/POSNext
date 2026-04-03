import { toNumber } from "./shared"

function toBoolean(value, fallback = true) {
	if (value === undefined || value === null || value === "") return fallback
	if (typeof value === "boolean") return value
	if (typeof value === "number") return value === 1
	if (typeof value === "string") {
		const normalized = value.trim().toLowerCase()
		if (["1", "true", "yes", "y"].includes(normalized)) return true
		if (["0", "false", "no", "n"].includes(normalized)) return false
	}
	return fallback
}

export function getItemDiscountPolicy(item = {}) {
	const explicitAllowed =
		item.discount_allowed ??
		item.allow_discount ??
		item.is_discount_allowed ??
		item.custom_allow_discount

	const explicitBlocked =
		item.discount_not_allowed ??
		item.is_discount_blocked ??
		item.custom_discount_not_allowed

	const discountAllowed =
		explicitBlocked !== undefined && explicitBlocked !== null
			? !toBoolean(explicitBlocked, false)
			: toBoolean(explicitAllowed, true)

	const maxDiscount = Math.max(
		0,
		toNumber(
			item.max_discount ??
			item.max_discount_allowed ??
			0
		)
	)

	return {
		discount_allowed: discountAllowed,
		max_discount: maxDiscount,
	}
}

export function normalizeDiscountPolicy(input = {}, context = {}) {
	const itemPolicy = getItemDiscountPolicy(context.item || input || {})
	return {
		discount_allowed: itemPolicy.discount_allowed,
		max_discount: itemPolicy.max_discount,
		discount_percentage: toNumber(input.discount_percentage),
		discount_amount: toNumber(input.discount_amount),
	}
}

export function getDiscountPolicyMessage(policy = {}) {
	if (!policy.discount_allowed) {
		return __("This item does not allow discount")
	}
	if (policy.max_discount > 0) {
		return __("Maximum allowed discount is {0}%", [policy.max_discount])
	}
	return ""
}

export function applyDiscountPolicy(line = {}, policyInput = {}, context = {}) {
	const subtotal = Math.max(
		0,
		toNumber(
			context.subtotal ??
			line.selected_display_subtotal ??
			line.amount ??
			(toNumber(line.rate) * toNumber(line.quantity || line.qty || 0))
		)
	)

	const policy = {
		...getItemDiscountPolicy(context.item || line || {}),
		...normalizeDiscountPolicy(policyInput, { item: context.item || line || {} }),
	}

	let discountPercentage = toNumber(policy.discount_percentage, toNumber(line.discount_percentage))
	let discountAmount = toNumber(policy.discount_amount, toNumber(line.discount_amount))

	if (!policy.discount_allowed) {
		discountPercentage = 0
		discountAmount = 0
	} else if (policy.max_discount > 0 && subtotal > 0) {
		const maxDiscountValue = (subtotal * policy.max_discount) / 100

		if (discountPercentage > policy.max_discount) {
			discountPercentage = policy.max_discount
		}

		if (discountAmount > maxDiscountValue) {
			discountAmount = maxDiscountValue
		}
	}

	return {
		...line,
		discount_percentage: discountPercentage,
		discount_amount: discountAmount,
	}
}
