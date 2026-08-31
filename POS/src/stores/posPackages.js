/**
 * @fileoverview POS Package ("Paket") store.
 *
 * Loads package definitions once per shift, caches them in IndexedDB, and
 * resolves a tapped catalog item to the package it represents.
 *
 * Quoting is server-authoritative when online. Offline it falls back to
 * `packageQuote.js`, which mirrors the Python implementation; either way the
 * server re-quotes on Sales Invoice validate.
 *
 * @module stores/posPackages
 */

import { call } from "@/utils/apiWrapper";
import { logger } from "@/utils/logger";
import { isOffline } from "@/utils/offline/offlineState";
import { offlineWorker } from "@/utils/offline/workerClient";
import { quotePackageLocally, selectionsToChoices } from "@/utils/packageQuote";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

const log = logger.create("POSPackages");

export const usePOSPackagesStore = defineStore("posPackages", () => {
	const packages = ref([]);
	const hasFetched = ref(false);
	const isLoading = ref(false);

	let fetchPromise = null;

	/** Package definitions keyed by their parent item_code. */
	const packagesByParentItem = computed(() => {
		const map = new Map();
		for (const pkg of packages.value) {
			map.set(pkg.parent_item, pkg);
		}
		return map;
	});

	/** Item codes that open the package dialog instead of being added directly. */
	const packageItemCodes = computed(() => new Set(packagesByParentItem.value.keys()));

	function isPackageItem(itemCode) {
		return packageItemCodes.value.has(itemCode);
	}

	function getPackageForItem(itemCode) {
		return packagesByParentItem.value.get(itemCode) || null;
	}

	function setPackages(list = []) {
		packages.value = Array.isArray(list) ? list : [];
	}

	function clearPackages() {
		packages.value = [];
		hasFetched.value = false;
		fetchPromise = null;
	}

	/**
	 * Load packages for a profile, from cache when offline.
	 * Concurrent calls share one in-flight request.
	 *
	 * @param {string} posProfile - POS Profile name
	 * @param {boolean} force - Refetch even if already loaded
	 * @returns {Promise<boolean>} True when packages are available
	 */
	async function ensurePackagesFetched(posProfile, force = false) {
		if (hasFetched.value && !force) return packages.value.length > 0;
		if (fetchPromise) return fetchPromise;
		if (!posProfile) return false;

		isLoading.value = true;
		fetchPromise = (async () => {
			try {
				if (isOffline()) {
					const cached = await offlineWorker.getCachedPackages(posProfile);
					setPackages(cached || []);
					hasFetched.value = true;
					return packages.value.length > 0;
				}

				const response = await call("pos_next.api.packages.get_packages", {
					pos_profile: posProfile,
				});
				const list = response?.message || response || [];
				setPackages(list);
				hasFetched.value = true;

				offlineWorker.cachePackages(list, posProfile).catch((error) => {
					log.warn("Failed to cache packages for offline use", error);
				});

				return list.length > 0;
			} catch (error) {
				log.error("Failed to load packages", error);
				hasFetched.value = true;
				return false;
			} finally {
				isLoading.value = false;
				fetchPromise = null;
			}
		})();

		return fetchPromise;
	}

	/**
	 * Price a selection. Uses the server when online so the preview matches what
	 * the invoice will charge; falls back to the local mirror when offline.
	 *
	 * @param {Object} pkg - Package definition
	 * @param {Object<string, Object<string, number>>} selections - group_key -> option_id -> qty
	 * @param {string} posProfile - POS Profile name
	 * @returns {Promise<{valid: boolean, error: string|null, total: number, lines: Array, snapshot: Object}>}
	 */
	async function quote(pkg, selections, posProfile) {
		const local = quotePackageLocally(pkg, selections);

		// Local validation failed — no point asking the server the same question.
		if (!local.valid || isOffline()) return local;

		try {
			const response = await call("pos_next.api.packages.quote_package", {
				package: pkg.name,
				choices: JSON.stringify(selectionsToChoices(selections)),
				pos_profile: posProfile,
			});
			const result = response?.message || response;
			if (!result) return local;

			return {
				valid: true,
				error: null,
				total: result.total,
				lines: result.lines,
				snapshot: result.snapshot,
			};
		} catch (error) {
			log.warn("Server quote failed, using local quote", error);
			return local;
		}
	}

	return {
		packages,
		hasFetched,
		isLoading,
		packagesByParentItem,
		packageItemCodes,
		isPackageItem,
		getPackageForItem,
		setPackages,
		clearPackages,
		ensurePackagesFetched,
		quote,
	};
});
