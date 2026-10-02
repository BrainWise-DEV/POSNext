/**
 * Payment utility functions
 */

/**
 * Get emoji icon for payment method type
 * @param {string} type - Payment method type
 * @returns {string} Emoji icon
 */
export function getPaymentIcon(type) {
	const iconMap = {
		Cash: "💵",
		Card: "💳",
		Bank: "🏦",
		Phone: "📱",
		Wallet: "👛",
		Credit: "💚",
		"Credit Card": "💳",
		"Debit Card": "💳",
		"Mobile Money": "📱",
		Check: "🧾",
		"Gift Card": "🎁",
	};
	return iconMap[type] || "💰";
}
