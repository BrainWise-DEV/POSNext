<template>
	<Dialog
		v-model="show"
		:options="{ title: __('Select Table'), size: 'lg' }"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">

				<!-- Loading -->
				<div v-if="loading" class="flex justify-center py-10">
					<svg class="animate-spin h-6 w-6 text-blue-600" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l5-5-5-5v4A12 12 0 004 12z"/>
					</svg>
				</div>

				<!-- Empty -->
				<div v-else-if="tables.length === 0" class="text-center py-10 text-gray-600">
					{{ __('No tables found') }}
				</div>

				<!-- Tables Grid -->
				<div v-else class="grid grid-cols-2 md:grid-cols-3 gap-3">
					<div
						v-for="table in tables"
						:key="table.name"
						@click="selectTable(table)"
						:class="[
							'rounded-lg border p-4 cursor-pointer transition-all',
							selectedTable?.name === table.name
								? 'border-blue-600 bg-blue-50'
								: 'border-gray-200 hover:border-blue-400',
							table.status !== 'Available' && 'opacity-60'
						]"
					>
						<div class="flex justify-between items-start">
							<div>
								<h4 class="font-semibold text-gray-900">
									{{ table.table_name }}
								</h4>
								<p class="text-xs text-gray-600">
									{{ __('Capacity: {0}', [table.capacity || 0]) }}
								</p>
							</div>

							<span
								class="text-xs px-2 py-0.5 rounded-full font-medium"
								:class="statusBadgeClass(table.status)"
							>
								{{ __(table.status) }}
							</span>
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
					:disabled="!selectedTable"
					@click="confirmSelection"
				>
					{{ __('Confirm') }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { Dialog, Button, createResource } from "frappe-ui"
import { ref, watch } from "vue"

const props = defineProps({
	modelValue: Boolean,
	branch: String,
})

const emit = defineEmits(["update:modelValue", "table-selected"])

const show = ref(props.modelValue)
const tables = ref([])
const selectedTable = ref(null)
const loading = ref(false)

/* -------------------------
   Resource: Load Tables
------------------------- */
const tablesResource = createResource({
	url: "pos_next.api.tables.get_tables",
	makeParams() {
		return {
			branch: props.branch,
		}
	},
	auto: false,
	onSuccess(data) {
		tables.value = data || []
	},
	onError(err) {
		console.error("Failed to load tables", err)
	},
})

/* -------------------------
   Watchers
------------------------- */
watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val) loadTables()
	}
)

watch(show, (val) => {
	emit("update:modelValue", val)
	if (!val) reset()
})

/* -------------------------
   Methods
------------------------- */
function loadTables() {
	loading.value = true
	tablesResource.reload().finally(() => {
		loading.value = false
	})
}

function selectTable(table) {
	if (table.status !== "Available") return
	selectedTable.value = table
}

function confirmSelection() {
	if (!selectedTable.value) return
	emit("table-selected", selectedTable.value)
	show.value = false
}

function reset() {
	selectedTable.value = null
}

/* -------------------------
   Helpers
------------------------- */
function statusBadgeClass(status) {
	switch (status) {
		case "Available":
			return "bg-green-100 text-green-800"
		case "Occupied":
			return "bg-red-100 text-red-800"
		default:
			return "bg-gray-100 text-gray-700"
	}
}
</script>
