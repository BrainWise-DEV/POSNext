/**
 * Item add ons (e.g. tinta mixed into a paint base) - rules live in nextend
 * (`nextend.item_addon`). The catalog is fetched while online and kept in
 * IndexedDB so add ons can still be picked offline.
 *
 * In the cart an add on hangs off its base line as `item.addons`
 * ([{ item_code, addon_group, item_name, amount }] - gelondongan has no
 * item_code) and is only expanded into separate Sales Invoice rows (carrier
 * item + custom_addon_* fields) on submission.
 */
import { call } from "@/utils/apiWrapper";
import { logger } from "@/utils/logger";
import { getSetting, setSetting } from "@/utils/offline/db";
import { ref } from "vue";

const log = logger.create("ItemAddons");
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
 * Add ons offered for a cart line, mirroring nextend.item_addon.resolve_addons:
 * `{ items: [{ item_code, item_name, addon_group }], groups: [name] }`.
 * A group is sold gelondongan (one price for all its tinta) and offered only
 * while one of its members is in the line's warehouse.
 */
export function getAvailableAddons(item) {
	const data = catalog.value;
	if (!data || !item?.item_code || item.is_free_item) return { items: [], groups: [] };

	const codes = new Set();
	const groups = new Set();
	for (const rule of data.rules) {
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
		override.add.forEach((code) => codes.add(code));
		override.exclude.forEach((code) => codes.delete(code));
	}
	codes.delete(item.item_code);

	const members = data.groups || {};
	const groupOf = {};
	for (const [group, list] of Object.entries(members)) {
		for (const code of list) groupOf[code] = group;
	}
	const inWarehouse = (code) => (data.bins[code] || []).includes(item.warehouse);

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

export function hasAvailableAddons(item) {
	const { items, groups } = getAvailableAddons(item);
	return items.length > 0 || groups.length > 0;
}

/** Cart key of an add on: the tinta, or the group when sold gelondongan. */
export function addonKey(addon) {
	return addon.item_code || `group:${addon.addon_group}`;
}

export function getAddonCarrierItem() {
	return catalog.value?.carrier_item || null;
}
