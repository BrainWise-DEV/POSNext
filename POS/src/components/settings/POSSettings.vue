<template>
	<!-- Full Page Overlay -->
	<Transition name="fade">
		<div
			v-if="show"
			class="fixed inset-0 bg-black bg-opacity-50 z-[300]"
			@click.self="handleClose"
		>
			<!-- Main Container -->
			<div class="fixed inset-0 flex items-center justify-center p-4 md:p-6">
				<div class="w-full max-w-5xl max-h-[90vh] bg-white rounded-xl shadow-2xl overflow-hidden flex flex-col">
					<!-- Header -->
					<div class="flex items-center justify-between px-6 py-5 border-b bg-gradient-to-r from-blue-50 to-indigo-50">
						<div class="flex items-center space-x-3">
							<div class="p-2 bg-blue-100 rounded-lg">
								<svg class="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
								</svg>
							</div>
							<div>
								<h2 class="text-xl font-bold text-gray-900">POS Settings</h2>
								<p class="text-sm text-gray-600 flex items-center mt-0.5">
									<svg class="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
									</svg>
									{{ settings.pos_profile || posProfile }}
								</p>
							</div>
						</div>
						<div class="flex items-center space-x-2">
							<Button
								@click="loadSettings"
								:loading="loading"
								variant="ghost"
								size="sm"
							>
								<template #prefix>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
									</svg>
								</template>
								Refresh
							</Button>
							<Button
								@click="saveSettings"
								:loading="saving"
								variant="solid"
								theme="blue"
							>
								<template #prefix>
									<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
									</svg>
								</template>
								Save Changes
							</Button>
							<button
								@click="handleClose"
								class="p-2 hover:bg-white/50 rounded-lg transition-colors"
							>
								<svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
								</svg>
							</button>
						</div>
					</div>

					<!-- Main Content -->
					<div class="flex-1 overflow-y-auto bg-gray-50">
						<!-- Loading State -->
						<div v-if="loading" class="flex flex-col items-center justify-center py-16">
							<div class="animate-spin rounded-full h-12 w-12 border-b-3 border-blue-500 mb-4"></div>
							<p class="text-sm font-medium text-gray-600">Loading settings...</p>
						</div>

						<!-- Settings Form -->
						<div v-else-if="settings.pos_profile || posProfile" class="p-6 space-y-6">
							<!-- Stock Settings Section - Prominent -->
							<div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
								<div :class="stockSectionClasses.header">
									<div class="flex items-center justify-between">
										<div class="flex items-center space-x-3">
											<div :class="stockSectionClasses.iconContainer">
												<svg :class="stockSectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.warehouse"/>
												</svg>
											</div>
											<div>
												<h3 class="text-lg font-bold text-gray-900">Stock Management</h3>
												<p class="text-xs text-gray-600 mt-0.5">Configure warehouse and inventory settings</p>
											</div>
										</div>
										<div :class="stockSectionClasses.badge">
											<svg :class="stockSectionClasses.badgeIcon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.checkCircle"/>
											</svg>
											<span :class="stockSectionClasses.badgeText">Stock Controls</span>
										</div>
									</div>
								</div>
								<div class="p-6 space-y-6">
									<!-- Warehouse Selection -->
									<div :class="warehouseSubsectionClasses.container">
										<div class="flex items-center space-x-2 mb-4">
											<svg :class="warehouseSubsectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.location"/>
											</svg>
											<h4 class="text-sm font-semibold text-gray-900">Warehouse Selection</h4>
										</div>
										<div v-if="warehouseOptions.length === 0" class="flex items-center p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
											<svg class="w-5 h-5 text-yellow-600 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.warning"/>
											</svg>
											<p class="text-sm text-yellow-800 font-medium">Loading warehouses...</p>
										</div>
										<SelectField
											v-else
											v-model="selectedWarehouse"
											label="Active Warehouse"
											:options="warehouseOptions"
											description="All stock operations will use this warehouse. Stock quantities will refresh after saving."
										/>
									</div>

									<!-- Stock Policy Settings -->
									<div :class="stockPolicySubsectionClasses.container">
										<div class="flex items-center space-x-2 mb-4">
											<svg :class="stockPolicySubsectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.clipboard"/>
											</svg>
											<h4 class="text-sm font-semibold text-gray-900">Stock Validation Policy</h4>
										</div>
										<div class="space-y-3">
											<CheckboxField
												v-model="settings.allow_negative_stock"
												label="Allow Negative Stock"
												description="Enable selling items even when stock reaches zero or below. Integrates with ERPNext stock settings."
											/>
											<div class="mt-3 p-3 bg-blue-100 rounded-md">
												<div class="flex items-start space-x-2">
													<svg class="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.info"/>
													</svg>
													<p class="text-xs text-blue-800 leading-relaxed">
														<strong>Note:</strong> When enabled, the system will allow sales even when stock quantity is zero or negative.
														This is useful for handling stock sync delays or backorders. All transactions are tracked in the stock ledger.
													</p>
												</div>
											</div>
										</div>
									</div>

									<!-- Background Stock Sync Settings -->
									<div :class="stockSyncSubsectionClasses.container">
										<div class="flex items-center space-x-2 mb-4">
											<svg :class="stockSyncSubsectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
											</svg>
											<h4 class="text-sm font-semibold text-gray-900">Background Stock Sync</h4>
											<div v-if="stockSyncStatus.enabled" class="ml-auto flex items-center px-2.5 py-1 bg-green-100 border border-green-300 rounded-full">
												<div class="w-2 h-2 bg-green-500 rounded-full animate-pulse mr-2"></div>
												<span class="text-xs font-medium text-green-800">Active</span>
											</div>
											<div v-else class="ml-auto flex items-center px-2.5 py-1 bg-gray-100 border border-gray-300 rounded-full">
												<div class="w-2 h-2 bg-gray-400 rounded-full mr-2"></div>
												<span class="text-xs font-medium text-gray-600">Inactive</span>
											</div>
										</div>

										<div class="space-y-4">
											<!-- Enable Sync Toggle -->
											<CheckboxField
												v-model="stockSyncEnabled"
												label="Enable Automatic Stock Sync"
												description="Periodically sync stock quantities from server in the background (runs in Web Worker)"
											/>

											<!-- Sync Interval -->
											<div v-if="stockSyncEnabled" class="pl-6 space-y-3 border-l-2 border-blue-200">
												<NumberField
													v-model="stockSyncIntervalSeconds"
													label="Sync Interval (seconds)"
													description="How often to check server for stock updates (minimum 10 seconds)"
													:min="10"
													:max="300"
													:step="10"
												/>

												<!-- Sync Status Info -->
												<div class="p-3 bg-blue-50 border border-blue-200 rounded-lg">
													<div class="flex items-start space-x-2">
														<svg class="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.info"/>
														</svg>
														<div class="text-xs text-blue-800 space-y-1">
															<p><strong>Status:</strong> {{ stockSyncStatus.enabled ? 'Running' : 'Stopped' }}</p>
															<p><strong>Items Tracked:</strong> {{ stockSyncStatus.itemCount || 0 }}</p>
															<p><strong>Warehouse:</strong> {{ stockSyncStatus.warehouse || 'Not set' }}</p>
															<p v-if="stockSyncStatus.lastSync">
																<strong>Last Sync:</strong> {{ formatSyncTime(stockSyncStatus.lastSync) }}
															</p>
															<p v-else><strong>Last Sync:</strong> Never</p>
														</div>
													</div>
												</div>

												<!-- Network Usage Info -->
												<div class="p-3 bg-gray-50 border border-gray-200 rounded-lg">
													<div class="flex items-start space-x-2">
														<svg class="w-4 h-4 text-gray-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
															<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
														</svg>
														<div class="text-xs text-gray-700">
															<p class="font-medium mb-1">Network Usage:</p>
															<p>~15 KB per sync cycle</p>
															<p>~{{ Math.round((3600 / stockSyncIntervalSeconds) * 15 / 1024) }} MB per hour</p>
														</div>
													</div>
												</div>
											</div>
										</div>
									</div>
								</div>
							</div>

							<!-- Sales Management Section - Prominent -->
							<div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
								<div :class="salesSectionClasses.header">
									<div class="flex items-center justify-between">
										<div class="flex items-center space-x-3">
											<div :class="salesSectionClasses.iconContainer">
												<svg :class="salesSectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.shoppingCart"/>
												</svg>
											</div>
											<div>
												<h3 class="text-lg font-bold text-gray-900">Sales Management</h3>
												<p class="text-xs text-gray-600 mt-0.5">Configure pricing, discounts, and sales operations</p>
											</div>
										</div>
										<div :class="salesSectionClasses.badge">
											<svg :class="salesSectionClasses.badgeIcon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.currency"/>
											</svg>
											<span :class="salesSectionClasses.badgeText">Sales Controls</span>
										</div>
									</div>
								</div>
								<div class="p-6 space-y-6">
									<!-- Pricing & Discounts -->
									<div :class="pricingSubsectionClasses.container">
										<div class="flex items-center space-x-2 mb-4">
											<svg :class="pricingSubsectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.tag"/>
											</svg>
											<h4 class="text-sm font-semibold text-gray-900">Pricing & Discounts</h4>
										</div>
										<div class="space-y-3">
											<NumberField
												v-model="settings.max_discount_allowed"
												label="Max Discount (%)"
												description="Maximum discount per item"
												:min="0"
												:max="100"
											/>
											<CheckboxField
												v-model="settings.use_percentage_discount"
												label="Use Percentage Discount"
												description="Show discounts as percentages"
											/>
											<CheckboxField
												v-model="settings.allow_user_to_edit_additional_discount"
												label="Allow Additional Discount"
												description="Enable cart-wide discount"
											/>
										</div>
									</div>

									<!-- Sales Operations -->
									<div :class="operationsSubsectionClasses.container">
										<div class="flex items-center space-x-2 mb-4">
											<svg :class="operationsSubsectionClasses.icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="icons.checkCircle"/>
											</svg>
											<h4 class="text-sm font-semibold text-gray-900">Sales Operations</h4>
										</div>
										<div class="space-y-3">
											<CheckboxField
												v-model="settings.allow_credit_sale"
												label="Allow Credit Sale"
												description="Enable sales on credit"
											/>
											<CheckboxField
												v-model="settings.allow_return"
												label="Allow Return"
												description="Enable product returns"
											/>
											<CheckboxField
												v-model="settings.allow_write_off_change"
												label="Allow Write Off Change"
												description="Write off small change amounts"
											/>
											<CheckboxField
												v-model="settings.allow_partial_payment"
												label="Allow Partial Payment"
												description="Enable partial payment for invoices"
											/>
											<CheckboxField
												v-model="settings.silent_print"
												label="Silent Print"
												description="Print without confirmation"
											/>
										</div>
									</div>
								</div>
							</div>

						</div>

						<!-- Empty State -->
						<div v-else class="flex flex-col items-center justify-center py-16 text-center">
							<svg class="w-16 h-16 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
							</svg>
							<p class="text-gray-600 font-medium">No POS Profile Selected</p>
							<p class="text-gray-500 text-sm mt-1">Please select a POS Profile to configure settings</p>
						</div>
					</div>
				</div>
			</div>
		</div>
	</Transition>
</template>

<script setup>
import CheckboxField from "@/components/settings/CheckboxField.vue"
import NumberField from "@/components/settings/NumberField.vue"
import SelectField from "@/components/settings/SelectField.vue"
import { Button, call, createResource, toast } from "frappe-ui"
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import {
	getSectionHeaderClasses,
	getSubsectionClasses,
	icons,
} from "./settingsConfig"
import { offlineWorker } from "@/utils/offline/workerClient"
import { logger } from "@/utils/logger"

const log = logger.create('POSSettings')

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	currentWarehouse: String,
})

const emit = defineEmits(["update:modelValue", "warehouse-changed"])

const show = ref(props.modelValue)

// State
const loading = ref(true)
const saving = ref(false)
const warehousesList = ref([])
const selectedWarehouse = ref(props.currentWarehouse || "")
const settings = ref({
	pos_profile: props.posProfile || "",
	enabled: 1,
	// Core Settings
	max_discount_allowed: 0,
	use_percentage_discount: 0,
	allow_user_to_edit_additional_discount: 0,
	allow_credit_sale: 0,
	allow_return: 0,
	allow_write_off_change: 0,
	allow_partial_payment: 0,
	silent_print: 0,
	allow_negative_stock: 0,
})

// Stock Sync Settings (localStorage persisted)
const stockSyncEnabled = ref(false)
const stockSyncIntervalSeconds = ref(60) // Default 60 seconds
const stockSyncStatus = ref({
	enabled: false,
	warehouse: null,
	itemCount: 0,
	intervalMs: 60000,
	lastSync: null,
	running: false
})

// Warehouse options
const warehouseOptions = computed(() => {
	if (warehousesList.value.length === 0) return []
	return warehousesList.value.map((w) => ({
		label: w.warehouse_name || w.name,
		value: w.name,
	}))
})

// Dynamic classes using configuration helpers (DRY principle)
const stockSectionClasses = computed(() => getSectionHeaderClasses("purple"))
const salesSectionClasses = computed(() => getSectionHeaderClasses("green"))
const warehouseSubsectionClasses = computed(() => getSubsectionClasses("gray"))
const stockPolicySubsectionClasses = computed(() =>
	getSubsectionClasses("blue"),
)
const stockSyncSubsectionClasses = computed(() => getSubsectionClasses("indigo"))
const pricingSubsectionClasses = computed(() => getSubsectionClasses("emerald"))
const operationsSubsectionClasses = computed(() => getSubsectionClasses("teal"))

// Resources
const warehousesResource = createResource({
	url: "pos_next.api.pos_profile.get_warehouses",
	makeParams() {
		return {
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	onSuccess(data) {
		const warehouses = data?.message || data || []
		warehousesList.value = warehouses
	},
	onError(error) {
		warehousesList.value = []
	},
})

const settingsResource = createResource({
	url: "pos_next.pos_next.doctype.pos_settings.pos_settings.get_pos_settings",
	makeParams() {
		return {
			pos_profile: props.posProfile,
		}
	},
	onSuccess(data) {
		if (data) {
			Object.assign(settings.value, data)
			settings.value.pos_profile = props.posProfile
		}
		loading.value = false
	},
	onError(error) {
		loading.value = false
		toast.create({
			title: "Error",
			text: "Failed to load settings",
			icon: "alert-circle",
			iconClasses: "text-red-600",
		})
	},
})

// Watchers
watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val) {
			loadSettings()
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
})

// Watch for currentWarehouse prop changes and always sync
watch(
	() => props.currentWarehouse,
	(newWarehouse) => {
		if (newWarehouse) {
			selectedWarehouse.value = newWarehouse
		}
	},
	{ immediate: true },
)

// Methods
function handleClose() {
	show.value = false
}

async function loadSettings() {
	if (!props.posProfile) return
	loading.value = true
	settings.value.pos_profile = props.posProfile

	// Always set the current warehouse from props (from current shift/profile)
	selectedWarehouse.value = props.currentWarehouse || ""

	try {
		// Load warehouses first using call API directly
		const warehousesData = await call(
			"pos_next.api.pos_profile.get_warehouses",
			{
				pos_profile: props.posProfile,
			},
		)

		// Handle frappe-ui call response format { message: [...] }
		warehousesList.value = warehousesData?.message || warehousesData || []

		// Load settings
		settingsResource.reload()
	} catch (error) {
		log.error("Error loading warehouses:", error)
		warehousesList.value = []
		// Still load settings even if warehouses fail
		settingsResource.reload()
	}
}

async function saveSettings() {
	if (!props.posProfile) {
		toast.create({
			title: "Error",
			text: "POS Profile not found",
			icon: "alert-circle",
			iconClasses: "text-red-600",
		})
		return
	}

	saving.value = true
	const oldWarehouse = props.currentWarehouse
	const warehouseChanged = selectedWarehouse.value !== oldWarehouse

	try {
		// Save POS Settings (without warehouse)
		const result = await call(
			"pos_next.pos_next.doctype.pos_settings.pos_settings.update_pos_settings",
			{
				pos_profile: props.posProfile,
				settings: settings.value,
			},
		)

		if (result) {
			Object.assign(settings.value, result)
			settings.value.pos_profile = props.posProfile
		}

		// Update warehouse in POS Profile if changed
		if (warehouseChanged && selectedWarehouse.value) {
			const warehouseResult = await call(
				"pos_next.api.pos_profile.update_warehouse",
				{
					pos_profile: props.posProfile,
					warehouse: selectedWarehouse.value,
				},
			)

			if (warehouseResult && warehouseResult.success) {
				// Emit event to parent to reload stock with new warehouse
				emit("warehouse-changed", selectedWarehouse.value)
			}
		}

		toast.create({
			title: "Success",
			text: warehouseChanged
				? "Settings saved and warehouse updated. Reloading stock..."
				: "Settings saved successfully",
			icon: "check",
			iconClasses: "text-green-600",
		})
	} catch (error) {
		log.error("Error saving settings:", error)
		toast.create({
			title: "Error",
			text: error.message || "Failed to save settings",
			icon: "alert-circle",
			iconClasses: "text-red-600",
		})
	} finally {
		saving.value = false
	}
}

// ============================================================================
// STOCK SYNC FUNCTIONS
// ============================================================================

// Load stock sync settings from localStorage
function loadStockSyncSettings() {
	try {
		const saved = localStorage.getItem('pos_stock_sync_settings')
		if (saved) {
			const parsed = JSON.parse(saved)
			stockSyncEnabled.value = parsed.enabled ?? false
			stockSyncIntervalSeconds.value = parsed.intervalSeconds ?? 60
		}
	} catch (error) {
		log.error('Failed to load stock sync settings:', error)
	}
}

// Save stock sync settings to localStorage
function saveStockSyncSettings() {
	try {
		localStorage.setItem('pos_stock_sync_settings', JSON.stringify({
			enabled: stockSyncEnabled.value,
			intervalSeconds: stockSyncIntervalSeconds.value
		}))
	} catch (error) {
		log.error('Failed to save stock sync settings:', error)
	}
}

// Update stock sync status
async function updateStockSyncStatus() {
	try {
		const status = await offlineWorker.getStockSyncStatus()
		stockSyncStatus.value = status
	} catch (error) {
		log.error('Failed to get stock sync status:', error)
	}
}

// Apply stock sync configuration to worker
async function applyStockSyncConfig() {
	try {
		const intervalMs = stockSyncIntervalSeconds.value * 1000

		if (stockSyncEnabled.value) {
			// Configure and start sync
			await offlineWorker.configureStockSync({
				intervalMs
			})
			await offlineWorker.startStockSync()
		} else {
			// Stop sync
			await offlineWorker.stopStockSync()
		}

		// Update status
		await updateStockSyncStatus()

		// Save to localStorage
		saveStockSyncSettings()
	} catch (error) {
		log.error('Failed to apply stock sync config:', error)
	}
}

// Format sync time for display
function formatSyncTime(timestamp) {
	if (!timestamp) return 'Never'

	const now = Date.now()
	const diff = now - timestamp

	if (diff < 60000) {
		return `${Math.floor(diff / 1000)}s ago`
	} else if (diff < 3600000) {
		return `${Math.floor(diff / 60000)}m ago`
	} else {
		const date = new Date(timestamp)
		return date.toLocaleTimeString()
	}
}

// Watch for changes and apply
watch(stockSyncEnabled, () => {
	applyStockSyncConfig()
})

watch(stockSyncIntervalSeconds, () => {
	if (stockSyncEnabled.value) {
		applyStockSyncConfig()
	}
})

// Lifecycle hooks
onMounted(async () => {
	// Load settings
	loadStockSyncSettings()

	// Update status initially
	await updateStockSyncStatus()

	// Poll status every 5 seconds
	const statusInterval = setInterval(() => {
		updateStockSyncStatus()
	}, 5000)

	// Cleanup on unmount
	onUnmounted(() => {
		clearInterval(statusInterval)
	})
})
</script>

<style scoped>
/* Fade transition for overlay */
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}
</style>
