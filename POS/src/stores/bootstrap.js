/**
 * Bootstrap Store
 *
 * Provides optimized initial data loading by fetching all startup data
 * in a single API call instead of multiple sequential calls.
 *
 * Usage:
 * 1. Call bootstrapStore.loadInitialData() early in app initialization
 * 2. Other stores can check bootstrapStore for preloaded data before making their own API calls
 *
 * Performance improvement: ~300-500ms faster initial load
 */

import { call } from "@/utils/apiWrapper"
import { logger } from "@/utils/logger"
import { defineStore } from "pinia"
import { ref } from "vue"

const log = logger.create("Bootstrap")

export const useBootstrapStore = defineStore("bootstrap", () => {
	// State
	const loaded = ref(false)
	const loading = ref(false)
	const data = ref(null)
	const error = ref(null)

	/**
	 * Load all initial data in a single API call
	 * @returns {Promise<Object|null>} Bootstrap data or null on error
	 */
	async function loadInitialData() {
		if (loaded.value) {
			log.debug("Bootstrap data already loaded")
			return data.value
		}

		if (loading.value) {
			log.debug("Bootstrap already loading, waiting...")
			// Wait for existing load to complete
			await new Promise((resolve) => {
				const checkLoaded = setInterval(() => {
					if (!loading.value) {
						clearInterval(checkLoaded)
						resolve()
					}
				}, 50)
			})
			return data.value
		}

		loading.value = true
		error.value = null

		try {
			log.info("Loading bootstrap data...")
			const result = await call("pos_next.api.bootstrap.get_initial_data", {})

			if (result?.success) {
				data.value = result
				loaded.value = true
				log.success("Bootstrap data loaded", {
					hasShift: !!result.shift,
					locale: result.locale,
				})
				return result
			} else {
				throw new Error("Bootstrap API returned unsuccessful response")
			}
		} catch (err) {
			log.error("Failed to load bootstrap data", err)
			error.value = err.message || "Failed to load initial data"
			return null
		} finally {
			loading.value = false
		}
	}

	/**
	 * Get preloaded locale or null if not available
	 */
	function getPreloadedLocale() {
		return data.value?.locale || null
	}

	/**
	 * Get preloaded shift data or null if not available
	 */
	function getPreloadedShift() {
		return data.value?.shift || null
	}

	/**
	 * Get preloaded POS profile data or null if not available
	 */
	function getPreloadedPOSProfile() {
		return data.value?.pos_profile || null
	}

	/**
	 * Get preloaded POS settings or null if not available
	 */
	function getPreloadedPOSSettings() {
		return data.value?.pos_settings || null
	}

	/**
	 * Get preloaded payment methods or empty array if not available
	 */
	function getPreloadedPaymentMethods() {
		return data.value?.payment_methods || []
	}

	/**
	 * Get preloaded precision settings or defaults if not available
	 * Settings from Date and Number Format section in System Settings
	 * @returns {{ currency: number, float: number, rounding_method: string, number_format: string }}
	 */
	function getPreloadedPrecision() {
		return data.value?.precision || {
			currency: 2,
			float: 3,
			rounding_method: null,
			number_format: null,
		}
	}

	/**
	 * Check if bootstrap data is available
	 */
	function hasBootstrapData() {
		return loaded.value && data.value !== null
	}

	/**
	 * Reset bootstrap state (useful for logout/login cycles)
	 */
	function reset() {
		loaded.value = false
		loading.value = false
		data.value = null
		error.value = null
	}

	return {
		// State
		loaded,
		loading,
		data,
		error,

		// Actions
		loadInitialData,
		getPreloadedLocale,
		getPreloadedShift,
		getPreloadedPOSProfile,
		getPreloadedPOSSettings,
		getPreloadedPaymentMethods,
		getPreloadedPrecision,
		hasBootstrapData,
		reset,
	}
})
