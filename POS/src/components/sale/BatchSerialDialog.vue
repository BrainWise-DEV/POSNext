<template>
	<Dialog
		v-model="show"
		:options="{ title: item?.has_batch_no ? __('Select Batch Numbers') : __('Select Serial Numbers'), size: 'lg' }"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- Item Info -->
				<div v-if="item" class="bg-blue-50 rounded-lg p-3">
					<div class="flex items-center gap-3">
						<div class="w-12 h-12 bg-gray-100 rounded-md flex-shrink-0 flex items-center justify-center overflow-hidden">
							<img
								v-if="item.image"
								:src="item.image"
								:alt="item.item_name"
								loading="lazy"
								class="w-full h-full object-cover"
							/>
							<svg v-else class="h-6 w-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
							</svg>
						</div>
						<div class="flex-1">
							<h3 class="text-sm font-semibold text-gray-900">{{ item.item_name }}</h3>
							<p class="text-xs text-gray-600">{{ item.item_code }}</p>
						</div>
					</div>
				</div>

				<!-- Batch Selection -->
				<div v-if="item?.has_batch_no">
					<label class="block text-sm font-medium text-gray-700 mb-2">
						{{ __('Select Batch Number') }}
					</label>
					<div class="flex flex-col gap-2 max-h-80 overflow-y-auto">
						<div
							v-for="batch in availableBatches"
							:key="batch.batch_no"
							@click="selectBatch(batch)"
							:class="[
								'border rounded-lg p-3 cursor-pointer transition-all',
								selectedBatch?.batch_no === batch.batch_no
									? 'border-blue-500 bg-blue-50'
									: 'border-gray-200 hover:border-blue-300'
							]"
						>
							<div class="flex items-start justify-between">
								<div class="flex-1">
									<h4 class="text-sm font-semibold text-gray-900">{{ batch.batch_no }}</h4>
									<div class="flex items-center gap-3 mt-1">
										<span class="text-xs text-gray-600">
											{{ __('Qty: {0}', [batch.qty]) }}
										</span>
										<span v-if="batch.expiry_date" class="text-xs text-gray-600">
											{{ __('Exp: {0}', [formatDate(batch.expiry_date)]) }}
										</span>
									</div>
								</div>
								<div v-if="selectedBatch?.batch_no === batch.batch_no" class="flex-shrink-0">
									<svg class="w-5 h-5 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
									</svg>
								</div>
							</div>
						</div>
					</div>
				</div>

				<!-- Serial Number Selection -->
				<div v-if="item?.has_serial_no">
					<!-- Header with count and actions -->
					<div class="flex items-center justify-between mb-2">
						<label class="block text-sm font-medium text-gray-700">
							{{ __('Select Serial Numbers') }}
							<span v-if="totalSelectedSerials > 0" class="ms-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
								{{ __("{0} selected", [totalSelectedSerials]) }}
							</span>
						</label>
						<div class="flex gap-2">
							<button
								v-if="selectedSerials.length > 0"
								type="button"
								@click="clearAllSerials"
								class="text-xs text-gray-600 hover:text-gray-800 font-medium"
							>
								{{ __('Clear All') }}
							</button>
							<button
								v-if="filteredSerials.length > 0 && selectedSerials.length < filteredSerials.length"
								type="button"
								@click="selectAllSerials"
								class="text-xs text-blue-600 hover:text-blue-800 font-medium"
							>
								{{ __('Select All') }}
							</button>
						</div>
					</div>

					<!-- Search Input -->
					<div class="relative mb-3">
						<input
							v-model="serialSearchQuery"
							type="text"
							:placeholder="__('Search serial numbers...')"
							class="w-full px-3 py-2 ps-9 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
						/>
						<svg class="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
						</svg>
					</div>

					<!-- Loading State -->
					<div v-if="isLoadingSerials" class="flex items-center justify-center py-8">
						<svg class="animate-spin h-6 w-6 text-blue-600" fill="none" viewBox="0 0 24 24">
							<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
							<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
						</svg>
						<span class="ms-2 text-sm text-gray-600">{{ __('Loading serial numbers...') }}</span>
					</div>

					<!-- Empty State -->
					<div v-else-if="availableSerials.length === 0" class="text-center py-8">
						<svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
						</svg>
						<p class="mt-2 text-sm text-gray-600">{{ __('No serial numbers available') }}</p>
					</div>

					<!-- No Results State -->
					<div v-else-if="filteredSerials.length === 0" class="text-center py-8">
						<svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
						</svg>
						<p class="mt-2 text-sm text-gray-600">{{ __('No serial numbers match your search') }}</p>
					</div>

					<!-- Serial Numbers List -->
					<div v-else class="flex flex-col gap-2 max-h-80 overflow-y-auto">
						<div
							v-for="serial in filteredSerials"
							:key="serial.serial_no"
							@click="toggleSerial(serial)"
							:class="[
								'border rounded-lg p-3 cursor-pointer transition-all',
								isSerialSelected(serial.serial_no)
									? 'border-blue-500 bg-blue-50'
									: 'border-gray-200 hover:border-blue-300'
							]"
						>
							<div class="flex items-center gap-3">
								<!-- Selection order badge (start) -->
								<span
									v-if="isSerialSelected(serial.serial_no)"
									class="flex-shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-medium"
								>
									{{ getSelectionOrder(serial.serial_no) }}
								</span>
								<!-- Serial info (center) -->
								<div class="flex-1 min-w-0 text-start">
									<h4 class="text-sm font-semibold text-gray-900">{{ serial.serial_no }}</h4>
									<p v-if="serial.warehouse" class="text-xs text-gray-600">
										{{ serial.warehouse }}
									</p>
								</div>
								<!-- Checkbox indicator (end) -->
								<div :class="[
									'flex-shrink-0 w-5 h-5 rounded border-2 flex items-center justify-center transition-all ms-auto',
									isSerialSelected(serial.serial_no)
										? 'bg-blue-600 border-blue-600'
										: 'border-gray-300 bg-white'
								]">
									<svg v-if="isSerialSelected(serial.serial_no)" class="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
									</svg>
								</div>
							</div>
						</div>
					</div>

				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex gap-2">
				<Button variant="subtle" @click="show = false">
					{{ __('Cancel') }}
				</Button>
				<Button
					variant="solid"
					@click="handleConfirm"
					:disabled="!isValid"
				>
					{{ __('Confirm') }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { Button, Dialog, createResource } from "frappe-ui"
import { computed, ref, watch } from "vue"
import { useSerialNumberStore } from "@/stores/serialNumber"
import { usePOSCartStore } from "@/stores/posCart"
import { getCachedBatchData, getCachedSerialData } from "@/utils/offline/items"
import { isOffline } from "@/utils/offline"

const props = defineProps({
	modelValue: Boolean,
	item: Object,
	quantity: {
		type: Number,
		default: 1,
	},
	warehouse: String,
	posProfile: String,
})

const emit = defineEmits(["update:modelValue", "batch-serial-selected"])

// Serial Number Store for caching
const serialStore = useSerialNumberStore()

// Cart store to check quantities already in cart
const cartStore = usePOSCartStore()

const show = ref(props.modelValue)
const warehouseBatches = ref([]) // Raw batches from warehouse
const availableSerials = ref([])
const selectedBatch = ref(null)
const selectedSerials = ref([])
const serialSearchQuery = ref("")

// Computed: Available batches with cart quantities subtracted
const availableBatches = computed(() => {
	return warehouseBatches.value.map((batch) => {
		// Find quantity of this batch already in cart
		const cartQtyForBatch = cartStore.invoiceItems
			.filter((item) =>
				item.item_code === props.item?.item_code &&
				item.batch_no === batch.batch_no
			)
			.reduce((sum, item) => sum + (item.quantity || 0), 0)

		return {
			...batch,
			qty: Math.max(0, batch.qty - cartQtyForBatch), // Available = warehouse - cart
		}
	}).filter((batch) => batch.qty > 0) // Only show batches with available qty
})

// Resource for loading batches with actual stock quantities
const batchesResource = createResource({
	url: "pos_next.api.items.get_item_details",
	makeParams() {
		return {
			item_code: props.item?.item_code,
			pos_profile: props.posProfile,
		}
	},
	auto: false,
	async onSuccess(data) {
		if (data && data.batch_no_data && Array.isArray(data.batch_no_data)) {
			// Store raw warehouse batch data
			warehouseBatches.value = data.batch_no_data.map((batch) => ({
				batch_no: batch.batch_no,
				qty: batch.batch_qty,
				expiry_date: batch.expiry_date,
				manufacturing_date: batch.manufacturing_date,
			}))
		}
	},
	onError(error) {
		console.error("Error loading batches:", error)
	},
})

watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val && props.item) {
			loadBatchesOrSerials()
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
	if (!val) {
		resetSelection()
	}
})

const totalSelectedSerials = computed(() => {
	return selectedSerials.value.length
})

const filteredSerials = computed(() => {
	if (!serialSearchQuery.value.trim()) {
		return availableSerials.value
	}
	const query = serialSearchQuery.value.toLowerCase().trim()
	return availableSerials.value.filter((serial) =>
		serial.serial_no.toLowerCase().includes(query)
	)
})

const isValid = computed(() => {
	if (props.item?.has_batch_no) {
		return selectedBatch.value !== null
	}
	if (props.item?.has_serial_no) {
		// Valid if at least one serial is selected
		return totalSelectedSerials.value >= 1
	}
	return true
})

// Use store loading state for serials
const isLoadingSerials = computed(() => serialStore.loading)

async function loadBatchesOrSerials() {
	if (props.item?.has_batch_no) {
		// Try cached data first when offline
		if (isOffline()) {
			const cachedBatches = await getCachedBatchData(props.item.item_code)
			if (cachedBatches && cachedBatches.length > 0) {
				warehouseBatches.value = cachedBatches.map((batch) => ({
					batch_no: batch.batch_no,
					qty: batch.batch_qty,
					expiry_date: batch.expiry_date,
					manufacturing_date: batch.manufacturing_date,
				}))
				return
			}
		}
		// Fetch from server when online
		batchesResource.reload()
	} else if (props.item?.has_serial_no) {
		// Try cached data first when offline
		if (isOffline()) {
			const cachedSerials = await getCachedSerialData(props.item.item_code)
			if (cachedSerials && cachedSerials.length > 0) {
				availableSerials.value = cachedSerials
				return
			}
		}
		// Set warehouse in store
		serialStore.setWarehouse(props.warehouse)
		// Fetch from store (uses cache if valid)
		const serials = await serialStore.fetchSerials(props.item.item_code)
		availableSerials.value = serials
	}
}

function selectBatch(batch) {
	selectedBatch.value = batch
}

function toggleSerial(serial) {
	const index = selectedSerials.value.findIndex(
		(s) => s.serial_no === serial.serial_no,
	)
	if (index > -1) {
		selectedSerials.value.splice(index, 1)
	} else {
		// Allow selecting multiple serial numbers without limit
		selectedSerials.value.push(serial)
	}
}

function isSerialSelected(serialNo) {
	return selectedSerials.value.some((s) => s.serial_no === serialNo)
}

function getSelectionOrder(serialNo) {
	return selectedSerials.value.findIndex((s) => s.serial_no === serialNo) + 1
}

function selectAllSerials() {
	// Add all filtered serials that aren't already selected
	filteredSerials.value.forEach((serial) => {
		if (!isSerialSelected(serial.serial_no)) {
			selectedSerials.value.push(serial)
		}
	})
}

function clearAllSerials() {
	selectedSerials.value = []
}

function handleConfirm() {
	const result = {}

	if (props.item?.has_batch_no && selectedBatch.value) {
		result.batch_no = selectedBatch.value.batch_no
	}

	if (props.item?.has_serial_no) {
		const selectedList = selectedSerials.value.map((s) => s.serial_no)
		result.serial_no = selectedList.join("\n")
		result.quantity = selectedList.length

		// Remove selected serials from cache (they're now in cart)
		serialStore.consumeSerials(props.item.item_code, selectedList)
	}

	emit("batch-serial-selected", result)
	show.value = false
}

function resetSelection() {
	selectedBatch.value = null
	selectedSerials.value = []
	serialSearchQuery.value = ""
	warehouseBatches.value = []
	// Don't clear availableSerials - it's managed by the store cache
}

function formatDate(dateStr) {
	if (!dateStr) return ""
	return new Date(dateStr).toLocaleDateString()
}
</script>
