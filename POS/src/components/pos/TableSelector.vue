<template>
	<div class="flex flex-col h-full bg-white dark:bg-gray-900 overflow-hidden">
		<!-- Header -->
		<div class="flex items-center justify-between p-4 border-b dark:border-gray-800">
			<div>
				<h2 class="text-lg font-semibold text-gray-900 dark:text-white">
					{{ __("Select Table") }}
				</h2>
				<p class="text-sm text-gray-500 dark:text-gray-400">
					{{ __("Choose a table to begin the order") }}
				</p>
			</div>

			<!-- Area Selector -->
			<div v-if="areas.length > 1" class="flex items-center space-x-2">
				<Button
					:variant="selectedArea === 'All' ? 'solid' : 'subtle'"
					size="sm"
					@click="selectedArea = 'All'"
				>
					{{ __("All") }}
				</Button>
				<Button
					v-for="area in areas"
					:key="area.name"
					:variant="selectedArea === area.name ? 'solid' : 'subtle'"
					size="sm"
					@click="selectedArea = area.name"
				>
					{{ area.area_name }}
				</Button>
			</div>
		</div>

		<!-- Tables Grid -->
		<div class="flex-1 overflow-y-auto p-4">
			<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
				<div
					v-for="table in filteredTables"
					:key="table.name"
					class="relative group cursor-pointer rounded-xl border-2 transition-all duration-200 aspect-square flex flex-col items-center justify-center p-4 hover:shadow-lg"
					:class="[
						table.status === 'Empty' ? 'border-green-200 bg-green-50 hover:border-green-400 dark:border-green-900/50 dark:bg-green-900/20 dark:hover:border-green-500' : '',
						table.status === 'Occupied' ? 'border-red-200 bg-red-50 hover:border-red-400 dark:border-red-900/50 dark:bg-red-900/20 dark:hover:border-red-500' : '',
						table.status === 'Reserved' ? 'border-yellow-200 bg-yellow-50 hover:border-yellow-400 dark:border-yellow-900/50 dark:bg-yellow-900/20 dark:hover:border-yellow-500' : '',
						table.status === 'Cleaning' ? 'border-blue-200 bg-blue-50 hover:border-blue-400 dark:border-blue-900/50 dark:bg-blue-900/20 dark:hover:border-blue-500' : ''
					]"
					@click="selectTable(table)"
				>
					<!-- Status Indicator -->
					<div
						class="absolute top-2 right-2 w-3 h-3 rounded-full"
						:class="[
							table.status === 'Empty' ? 'bg-green-500' : '',
							table.status === 'Occupied' ? 'bg-red-500' : '',
							table.status === 'Reserved' ? 'bg-yellow-500' : '',
							table.status === 'Cleaning' ? 'bg-blue-500' : ''
						]"
					></div>

					<FeatherIcon name="coffee" class="w-8 h-8 mb-3 text-gray-700 dark:text-gray-300" />
					<span class="font-bold text-lg text-gray-900 dark:text-white text-center">{{ table.table_name }}</span>

					<div class="mt-2 text-xs font-medium px-2 py-1 rounded-full bg-white/60 dark:bg-gray-800/60 text-gray-700 dark:text-gray-300">
						{{ table.capacity }} {{ __("Seats") }}
					</div>

					<span class="mt-1 text-xs text-gray-500 dark:text-gray-400 font-medium">
						{{ __(table.status) }}
					</span>
				</div>
			</div>

			<div v-if="filteredTables.length === 0" class="flex flex-col items-center justify-center h-full text-gray-500">
				<FeatherIcon name="grid" class="w-12 h-12 mb-4 text-gray-300" />
				<p>{{ __("No tables found in this area") }}</p>
			</div>
		</div>
	</div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue"
import { useRestaurantStore } from "@/stores/restaurant"
import { usePOSCartStore } from "@/stores/posCart"
import { usePOSDraftsStore } from "@/stores/posDrafts"
import { Button, FeatherIcon } from "frappe-ui"

const emit = defineEmits(["table-selected"])

const restaurantStore = useRestaurantStore()
const cartStore = usePOSCartStore()
const draftsStore = usePOSDraftsStore()

const selectedArea = ref(null)

const areas = computed(() => restaurantStore.areas)
const tables = computed(() => restaurantStore.tables)

const filteredTables = computed(() => {
	if (!selectedArea.value || selectedArea.value === 'All') return tables.value
	return tables.value.filter(t => t.area === selectedArea.value)
})

onMounted(async () => {
	await restaurantStore.loadTablesAndAreas()

	// If empty from cache, try fetching from network directly
	if (areas.value.length === 0 || tables.value.length === 0) {
		await restaurantStore.fetchFromNetwork()
	}

	if (areas.value.length > 0) {
		selectedArea.value = 'All'
	}
})

const selectTable = async (table) => {
	// First, ensure cart is clean before entering a new table to avoid product mixups
	cartStore.clearCart()

	// Check if this table has an active draft
	await draftsStore.loadDrafts()
	const tableDraft = draftsStore.drafts.find(d => d.restaurant_table === table.name)

	if (tableDraft) {
		// Emit a special event so POSSale can handle draft loading gracefully
		emit("load-table-draft", tableDraft)
	} else {
		// Set the table in the cart
		cartStore.setRestaurantTable(table)

		// Automatically update table status if it's empty
		if (table.status === "Empty") {
			await restaurantStore.updateTableStatus(table.name, "Occupied")
		}

		emit("table-selected", table)
	}
}
</script>
