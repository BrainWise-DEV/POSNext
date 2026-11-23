/**
 * @fileoverview UUID generation utilities for offline invoice deduplication.
 * This file is shared between the main thread and web workers.
 * @module utils/offline/uuid
 */

/**
 * Generate a UUID v4 using crypto.randomUUID() if available,
 * otherwise falls back to a custom implementation.
 * @returns {string} UUID v4 string
 */
export const generateUUID = () => {
	if (typeof crypto !== "undefined" && crypto.randomUUID) {
		return crypto.randomUUID();
	}

	// Fallback implementation for older browsers/environments
	return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
		const r = (Math.random() * 16) | 0;
		const v = c === "x" ? r : (r & 0x3) | 0x8;
		return v.toString(16);
	});
};

/**
 * Generate a unique offline ID for invoice deduplication.
 * Format: pos_offline_<uuid>
 * @returns {string} Unique offline ID
 */
export const generateOfflineId = () => `pos_offline_${generateUUID()}`;

/**
 * The offline_id an offline sale is queued under: the cart's own (Ruling 136 (d)), so
 * paying a restored cart again finds the sale already queued, else a new one.
 * @param {{ offline_id?: string }} invoiceData
 * @returns {string}
 */
export const queuedOfflineId = (invoiceData) => {
	const given = invoiceData?.offline_id;
	return typeof given === "string" && /^pos_offline_[\w-]+$/.test(given) ? given : generateOfflineId();
};

/**
 * Generate a unique offline ID for expense deduplication.
 * Format: pos_expense_<uuid>
 * @returns {string} Unique offline expense ID
 */
export const generateOfflineExpenseId = () => `pos_expense_${generateUUID()}`;
