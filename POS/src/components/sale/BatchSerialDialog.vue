<template>
	<Dialog
		v-model="show"
		:options="{ title: `Select ${item?.has_batch_no ? 'Batch' : 'Serial'} Numbers`, size: 'lg' }"
	>
		<template #body-content>
			<div class="space-y-4">
				<!-- Item Info -->
				<div v-if="item" class="bg-blue-50 rounded-lg p-3">
					<div class="flex items-center space-x-3">
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
						<div class="text-right">
							<p class="text-sm font-bold text-gray-900">Qty: {{ quantity }}</p>
						</div>
					</div>
				</div>

				<!-- Batch Selection -->
				<div v-if="item?.has_batch_no">
					<label class="block text-sm font-medium text-gray-700 mb-2">
						Select Batch Number
					</label>
					<div class="space-y-2 max-h-80 overflow-y-auto">
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
									<div class="flex items-center space-x-3 mt-1">
										<span class="text-xs text-gray-600">
											Qty: {{ batch.qty }}
										</span>
										<span v-if="batch.expiry_date" class="text-xs text-gray-600">
											Exp: {{ formatDate(batch.expiry_date) }}
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
					<label class="block text-sm font-medium text-gray-700 mb-2">
						Select Serial Numbers ({{ selectedSerials.length }}/{{ quantity }})
					</label>
					<div class="space-y-2 max-h-80 overflow-y-auto">
						<div
							v-for="serial in availableSerials"
							:key="serial.serial_no"
							@click="toggleSerial(serial)"
							:class="[
								'border rounded-lg p-3 cursor-pointer transition-all',
								isSerialSelected(serial.serial_no)
									? 'border-blue-500 bg-blue-50'
									: 'border-gray-200 hover:border-blue-300'
							]"
						>
							<div class="flex items-center justify-between">
								<div class="flex-1">
									<h4 class="text-sm font-semibold text-gray-900">{{ serial.serial_no }}</h4>
									<p v-if="serial.warehouse" class="text-xs text-gray-600 mt-1">
										Warehouse: {{ serial.warehouse }}
									</p>
								</div>
								<div v-if="isSerialSelected(serial.serial_no)" class="flex-shrink-0">
									<svg class="w-5 h-5 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
									</svg>
								</div>
							</div>
						</div>
					</div>

					<!-- Manual Serial Entry -->
					<div class="mt-3 p-3 bg-gray-50 rounded-lg">
						<label class="block text-xs font-medium text-gray-700 mb-2">
							Or enter serial numbers manually (one per line)
						</label>
						<textarea
							v-model="manualSerials"
							rows="3"
							placeholder="Enter serial numbers..."
							class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
						></textarea>
					</div>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex space-x-2">
				<Button variant="subtle" @click="show = false">
					Cancel
				</Button>
				<Button
					variant="solid"
					@click="handleConfirm"
					:disabled="!isValid"
				>
					Confirm
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Dialog, Button, createResource } from 'frappe-ui'

const props = defineProps({
	modelValue: Boolean,
	item: Object,
	quantity: {
		type: Number,
		default: 1
	},
	warehouse: String,
})

const emit = defineEmits(['update:modelValue', 'batch-serial-selected'])

const show = ref(props.modelValue)
const availableBatches = ref([])
const availableSerials = ref([])
const selectedBatch = ref(null)
const selectedSerials = ref([])
const manualSerials = ref('')

// Resource for loading batches
const batchesResource = createResource({
	url: 'frappe.client.get_list',
	makeParams() {
		return {
			doctype: 'Batch',
			filters: {
				item: props.item?.item_code,
				disabled: 0
			},
			fields: ['name as batch_no', 'expiry_date'],
			limit_page_length: 100
		}
	},
	auto: false,
	async onSuccess(data) {
		if (data && Array.isArray(data)) {
			// For simplicity, set qty to 999 for all batches
			// In production, you'd want to query actual stock
			availableBatches.value = data.map(batch => ({
				...batch,
				qty: 999
			}))
		}
	},
	onError(error) {
		console.error('Error loading batches:', error)
	}
})

// Resource for loading serials
const serialsResource = createResource({
	url: 'frappe.client.get_list',
	makeParams() {
		return {
			doctype: 'Serial No',
			filters: {
				item_code: props.item?.item_code,
				warehouse: props.warehouse,
				status: 'Active'
			},
			fields: ['name as serial_no', 'warehouse'],
			limit_page_length: 100
		}
	},
	auto: false,
	onSuccess(data) {
		if (data && Array.isArray(data)) {
			availableSerials.value = data
		}
	},
	onError(error) {
		console.error('Error loading serials:', error)
	}
})

watch(() => props.modelValue, (val) => {
	show.value = val
	if (val && props.item) {
		loadBatchesOrSerials()
	}
})

watch(show, (val) => {
	emit('update:modelValue', val)
	if (!val) {
		resetSelection()
	}
})

const isValid = computed(() => {
	if (props.item?.has_batch_no) {
		return selectedBatch.value !== null
	}
	if (props.item?.has_serial_no) {
		const totalSerials = selectedSerials.value.length +
			(manualSerials.value ? manualSerials.value.split('\n').filter(s => s.trim()).length : 0)
		return totalSerials === props.quantity
	}
	return true
})

function loadBatchesOrSerials() {
	if (props.item?.has_batch_no) {
		batchesResource.reload()
	} else if (props.item?.has_serial_no) {
		serialsResource.reload()
	}
}

function selectBatch(batch) {
	selectedBatch.value = batch
}

function toggleSerial(serial) {
	const index = selectedSerials.value.findIndex(s => s.serial_no === serial.serial_no)
	if (index > -1) {
		selectedSerials.value.splice(index, 1)
	} else if (selectedSerials.value.length < props.quantity) {
		selectedSerials.value.push(serial)
	}
}

function isSerialSelected(serialNo) {
	return selectedSerials.value.some(s => s.serial_no === serialNo)
}

function handleConfirm() {
	const result = {}

	if (props.item?.has_batch_no && selectedBatch.value) {
		result.batch_no = selectedBatch.value.batch_no
	}

	if (props.item?.has_serial_no) {
		const manualList = manualSerials.value
			? manualSerials.value.split('\n').filter(s => s.trim()).map(s => s.trim())
			: []
		const selectedList = selectedSerials.value.map(s => s.serial_no)
		result.serial_no = [...selectedList, ...manualList].join('\n')
	}

	emit('batch-serial-selected', result)
	show.value = false
}

function resetSelection() {
	selectedBatch.value = null
	selectedSerials.value = []
	manualSerials.value = ''
	availableBatches.value = []
	availableSerials.value = []
}

function formatDate(dateStr) {
	if (!dateStr) return ''
	return new Date(dateStr).toLocaleDateString()
}
</script>
