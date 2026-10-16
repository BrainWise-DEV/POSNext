/**
 * Item add ons (e.g. tinta mixed into a paint base) - rules live in nextend
 * (`nextend.item_addon`). The catalog is fetched while online and kept in
 * IndexedDB so add ons can still be picked offline.
 *
 * Each rule has a `jenis`:
 * - "Tinta Produksi": a tinted base stays one cart line; `item.tinting`
 *   ({ hpp_tinta, job }) holds the tinta cost read off the tinting machine
 *   (not revenue) and the machine's job number, submitted as
 *   custom_hpp_tinta / custom_tinting_job. The base price is open
 *   (`isOpenPriceItem`).
 * - "Add On Jual": services charged on top of the line, kept on the line as
 *   `item.addons` ([{ item_code, item_name, amount }]) and only expanded into
 *   separate Sales Invoice rows (carrier item + custom_addon_* fields) on
 *   submission.
 */
import { call } from "@/utils/apiWrapper";
import { logger } from "@/utils/logger";
import { getSetting, setSetting } from "@/utils/offline/db";
import { ref } from "vue";

const log = logger.create("ItemAddons");
export const JENIS_TINTA = "Tinta Produksi";
export const JENIS_JUAL = "Add On Jual";
const CATALOG_KEY = "item_addon_catalog";

const catalog = ref(null);

export async function refreshAddonCatalog() {
	try {
		const data = await call("nextend.item_addon.get_addon_catalog");
		catalog.value = data?.message || data || null;
		await setSetting(CATALOG_KEY, catalog.value);
	} catch (error) {
		log.warn("Add on catalog unavailable, using cached copy", error);
		await loadCachedAddonCatalog();
	}
}

export async function loadCachedAddonCatalog() {
	if (!catalog.value) {
		catalog.value = await getSetting(CATALOG_KEY, null);
	}
}

/**
 * Add ons of `jenis` offered for a cart line, mirroring
 * nextend.item_addon.resolve_addons:
 * `{ items: [{ item_code, item_name, addon_group }], groups: [name] }`.
 * Tinta must have a Bin in the line's warehouse, and a group is offered only
 * while one of its members does; services (Add On Jual) have no Bin and no group.
 */
export function getAvailableAddons(item, jenis = JENIS_TINTA) {
	const data = catalog.value;
	if (!data || !item?.item_code || item.is_free_item) return { items: [], groups: [] };

	const isTinta = jenis === JENIS_TINTA;
	const services = new Set(data.service_items || []);
	const codes = new Set();
	const groups = new Set();
	for (const rule of data.rules) {
		// Catalogs cached before jenis existed only had tinta rules
		if ((rule.jenis || JENIS_TINTA) !== jenis) continue;
		const bases = rule.bases;
		if (
			bases.Item.includes(item.item_code) ||
			(item.brand && bases.Brand.includes(item.brand)) ||
			(item.item_group && bases["Item Group"].includes(item.item_group))
		) {
			rule.addons.forEach((code) => codes.add(code));
			(rule.groups || []).forEach((group) => groups.add(group));
		}
	}
	const override = data.overrides[item.item_code];
	if (override) {
		// One override table serves both kinds: an item counts for its own kind
		const ownKind = (code) => services.has(code) !== isTinta;
		override.add.filter(ownKind).forEach((code) => codes.add(code));
		override.exclude.filter(ownKind).forEach((code) => codes.delete(code));
	}
	codes.delete(item.item_code);

	const members = data.groups || {};
	const groupOf = {};
	for (const [group, list] of Object.entries(members)) {
		for (const code of list) groupOf[code] = group;
	}
	const inWarehouse = (code) => !isTinta || (data.bins[code] || []).includes(item.warehouse);

	return {
		items: [...codes]
			.filter(inWarehouse)
			.sort()
			.map((code) => ({
				item_code: code,
				item_name: data.item_names[code] || code,
				addon_group: groupOf[code] || null,
			})),
		groups: [...groups].filter((group) => (members[group] || []).some(inWarehouse)).sort(),
	};
}

/**
 * A base can be tinted when the tinta offered for it in its warehouse all come
 * from one brand (the machine's) - mirrors nextend.item_addon.is_tintable.
 * Item Add On Rule pairs base and tinta brand; their names differ.
 */
export function isTintable(item) {
	const data = catalog.value;
	if (!data) return false;
	const { items, groups } = getAvailableAddons(item);
	const inWarehouse = (code) => (data.bins[code] || []).includes(item.warehouse);
	const codes = [
		...items.map((row) => row.item_code),
		...groups.flatMap((group) => (data.groups[group] || []).filter(inWarehouse)),
	];
	const brands = new Set(codes.map((code) => data.item_brands?.[code]).filter(Boolean));
	return brands.size === 1;
}

export function hasAvailableAddons(item, jenis = JENIS_JUAL) {
	const { items, groups } = getAvailableAddons(item, jenis);
	return items.length > 0 || groups.length > 0;
}

/** Cart key of an add on: the item, or the group when sold gelondongan (old invoices). */
export function addonKey(addon) {
	return addon.item_code || `group:${addon.addon_group}`;
}

export function getAddonCarrierItem() {
	return catalog.value?.carrier_item || null;
}

/** Price may be typed by the cashier/SPG (nextend Item.custom_allow_open_price). */
export function isOpenPriceItem(itemCode) {
	return Boolean(itemCode && catalog.value?.open_price_items?.includes(itemCode));
}
