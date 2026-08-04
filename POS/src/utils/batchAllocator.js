/**
 * Batch Allocation Utility
 *
 * Splits a requested quantity across a batch-tracked item's available
 * batches (FIFO/expiry order) so a single cart line never needs more stock
 * than one batch actually has. The item's own already-selected batch is
 * filled first; any remainder spills into the next available batch(es).
 */

import { call } from "frappe-ui";

/**
 * Map the raw batch_no_data returned by pos_next.api.items.get_item_details
 * into the shape used throughout the batch dialog/allocator.
 *
 * @param {Array} batchNoData
 * @returns {Array} [{batch_no, qty, expiry_date, manufacturing_date, msp, mrp}]
 */
export function mapWarehouseBatches(batchNoData) {
	if (!Array.isArray(batchNoData)) return [];
	return batchNoData.map((batch) => ({
		batch_no: batch.batch_no,
		qty: batch.batch_qty ?? batch.qty ?? 0,
		expiry_date: batch.expiry_date,
		manufacturing_date: batch.manufacturing_date,
		msp: Number(batch.msp) || 0,
		mrp: Number(batch.mrp) || 0,
	}));
}

/**
 * Fetch a fresh, FIFO-sorted, price-enriched batch list for an item — the
 * same two calls the batch-selection dialog makes, for use when the cart
 * needs to auto-split a quantity increase across batches and can't trust
 * whatever batch list it last saw (draft reload, stale selection, etc.).
 *
 * @param {Object} params
 * @param {string} params.itemCode
 * @param {string} params.posProfile
 * @param {string} params.priceList
 * @param {string} params.uom
 * @returns {Promise<Array>} FIFO-sorted [{batch_no, qty, expiry_date, manufacturing_date, msp, mrp}]
 */
export async function fetchBatchesForItem({ itemCode, posProfile, priceList, uom }) {
	const details = await call("pos_next.api.items.get_item_details", {
		item_code: itemCode,
		pos_profile: posProfile,
	});
	const batches = mapWarehouseBatches(details?.batch_no_data);
	if (!batches.length) return [];

	try {
		const priceMap = await call("pos_next.api.items.get_batch_prices_for_item", {
			item_code: itemCode,
			batch_nos: JSON.stringify(batches.map((b) => b.batch_no)),
			price_list: priceList,
			uom,
		});
		const withPrices = batches.map((batch) => {
			const prices = priceMap?.[batch.batch_no] || {};
			return {
				...batch,
				msp: Number(prices.msp) || batch.msp || 0,
				mrp: Number(prices.mrp) || batch.mrp || 0,
			};
		});
		return sortBatchesFifo(withPrices);
	} catch (error) {
		console.error("Error loading batch prices:", error);
		return sortBatchesFifo(batches);
	}
}

/**
 * Sort batches FIFO — earliest expiry first, then earliest manufacturing
 * date. Batches missing either date sort last (nulls last).
 *
 * @param {Array} batches - [{batch_no, qty, expiry_date, manufacturing_date, msp, mrp}]
 * @returns {Array} new sorted array (input is not mutated)
 */
export function sortBatchesFifo(batches) {
	if (!Array.isArray(batches)) return [];
	const toTime = (d) => (d ? new Date(d).getTime() : Infinity);
	return [...batches].sort((a, b) => {
		const expiryDiff = toTime(a.expiry_date) - toTime(b.expiry_date);
		if (expiryDiff !== 0) return expiryDiff;
		return toTime(a.manufacturing_date) - toTime(b.manufacturing_date);
	});
}

/**
 * Net quantity of a batch still available to allocate: its raw warehouse
 * qty minus whatever quantity OTHER cart rows for the same item already
 * hold against that batch (the row currently being resized doesn't count
 * against itself).
 *
 * @param {Object} batch - {batch_no, qty}
 * @param {string} itemCode
 * @param {Array} invoiceItems - current cart rows
 * @param {string} resizingBatchNo - batch_no of the row being resized
 * @returns {number}
 */
function netBatchQty(batch, itemCode, invoiceItems, resizingBatchNo) {
	const usedByOtherRows = (invoiceItems || [])
		.filter(
			(row) =>
				row.item_code === itemCode &&
				row.batch_no === batch.batch_no &&
				row.batch_no !== resizingBatchNo
		)
		.reduce((sum, row) => sum + (row.quantity || 0), 0);
	return Math.max(0, (batch.qty || 0) - usedByOtherRows);
}

/**
 * Allocate a requested quantity across an item's available batches.
 *
 * @param {Object} params
 * @param {Object} params.item - cart row being resized (item_code, batch_no)
 * @param {number} params.requestedQty - new total quantity requested for this item's batch line
 * @param {Array} params.freshBatches - full batch list for the item: [{batch_no, qty, expiry_date, manufacturing_date, msp, mrp}]
 * @param {Array} params.invoiceItems - current cart rows (to net out qty already allocated elsewhere)
 * @returns {{allocations: Array<{batch_no: string, qty: number, msp: number, mrp: number}>, shortfall: number}}
 *          shortfall > 0 means the combined available stock across every known batch
 *          couldn't fully cover requestedQty — allocations already reflect the capped total.
 */
export function allocateQuantity({ item, requestedQty, freshBatches, invoiceItems }) {
	const itemCode = item.item_code;
	const ownBatchNo = item.batch_no;
	const sorted = sortBatchesFifo(freshBatches);

	const ownBatch = sorted.find((b) => b.batch_no === ownBatchNo);
	const otherBatches = sorted.filter((b) => b.batch_no !== ownBatchNo);

	let remaining = requestedQty;
	const allocations = [];

	if (ownBatch) {
		const available = netBatchQty(ownBatch, itemCode, invoiceItems, ownBatchNo);
		const qty = Math.min(remaining, available);
		if (qty > 0) {
			allocations.push({ batch_no: ownBatch.batch_no, qty, msp: ownBatch.msp, mrp: ownBatch.mrp });
			remaining -= qty;
		}
	}

	for (const batch of otherBatches) {
		if (remaining <= 0) break;
		const available = netBatchQty(batch, itemCode, invoiceItems, ownBatchNo);
		if (available <= 0) continue;
		const qty = Math.min(remaining, available);
		allocations.push({ batch_no: batch.batch_no, qty, msp: batch.msp, mrp: batch.mrp });
		remaining -= qty;
	}

	return { allocations, shortfall: Math.max(0, remaining) };
}
