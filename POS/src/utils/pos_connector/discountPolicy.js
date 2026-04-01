import { toNumber } from "./shared"

export function normalizeDiscountPolicy(input = {}) {
	return {
		discount_percentage: toNumber(input.discount_percentage),
		discount_amount: toNumber(input.discount_amount),
	}
}

export function applyDiscountPolicy(line = {}, policy = {}) {
	return {
		...line,
		discount_percentage: toNumber(policy.discount_percentage, toNumber(line.discount_percentage)),
		discount_amount: toNumber(policy.discount_amount, toNumber(line.discount_amount)),
	}
}