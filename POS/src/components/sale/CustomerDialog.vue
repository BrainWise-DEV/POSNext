<template>
	<Dialog v-model="show" :options="{ title: __('Select Customer'), size: 'md' }">
		<template #body-title>
			<span class="sr-only">{{
				__("Search and select a customer for the transaction")
			}}</span>
		</template>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- Search Input -->
				<div class="relative">
					<!-- Search Icon -->
					<div
						class="absolute inset-y-0 start-0 ps-1 flex items-center pointer-events-none"
					>
						<svg
							class="h-5 w-5 text-gray-400"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
							/>
						</svg>
					</div>
					<!-- Search Input -->
					<input
						id="customer-search"
						name="customer-search"
						:value="searchTerm"
						@input="handleSearchInput"
						type="text"
						:placeholder="__('Search customers by name, mobile, or email...')"
						class="w-full border border-gray-300 rounded-md ps-6 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
						@keydown="handleKeydown"
						autofocus
						autocomplete="off"
						:aria-label="__('Search customers')"
					/>
					<!-- Clear Button -->
					<button
						v-if="searchTerm"
						@click="customerStore.clearSearch()"
						class="absolute inset-y-0 end-0 text-gray-400 hover:text-gray-600"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M6 18L18 6M6 6l12 12"
							/>
						</svg>
					</button>
				</div>
				<p
					v-if="!loading && allCustomers.length > 0"
					class="text-start text-xs text-gray-500 mt-0"
				>
					<span v-if="showingRecent" class="text-blue-600 font-medium"
						>⭐ {{ __("Recent & Frequent") }}</span
					>
					<span v-else>{{
						__("{0} of {1} customers", [customers.length, allCustomers.length])
					}}</span>
					<span v-if="customers.length > 0" class="text-gray-400 ms-1">{{
						__("• Use ↑↓ to navigate, Enter to select")
					}}</span>
				</p>

				<!-- Smart Recommendations -->
				<div v-if="recommendations.length > 0" class="flex flex-wrap gap-2 -mt-2">
					<div
						v-for="rec in recommendations"
						:key="rec.type"
						class="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 text-blue-700 rounded-md text-xs"
					>
						<span>{{ rec.icon }}</span>
						<span>{{ rec.text }}</span>
					</div>
				</div>

				<!-- Customers List - Optimized rendering -->
				<div class="max-h-96 overflow-y-auto" style="will-change: scroll-position">
					<div v-if="loading" class="text-center py-8">
						<div
							class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"
						></div>
						<p class="mt-2 text-sm text-gray-500">{{ __("Loading customers...") }}</p>
					</div>

					<div
						v-else-if="allCustomers.length === 0 && !loading"
						class="text-center py-8"
					>
						<svg
							class="mx-auto h-12 w-12 text-gray-400"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"
							/>
						</svg>
						<p class="mt-2 text-sm text-gray-500">
							{{ __("No customers available") }}
						</p>
						<p class="text-xs text-gray-400 mt-1">
							{{ __("Create your first customer to get started") }}
						</p>
					</div>

					<div
						v-else-if="customers.length === 0 && searchTerm.trim().length > 0"
						class="text-center py-8"
					>
						<svg
							class="mx-auto h-12 w-12 text-gray-400"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
							/>
						</svg>
						<p class="mt-2 text-sm font-medium text-gray-700">
							{{ __('No results for "{0}"', [searchTerm]) }}
						</p>
						<p class="text-xs text-gray-500 mt-1">
							{{ __("Try a different search term or create a new customer") }}
						</p>
					</div>

					<!-- Optimized list rendering with v-memo for performance -->
					<div v-else class="flex flex-col gap-2">
						<button
							v-for="(customer, index) in customers"
							:key="customer.name"
							v-memo="[customer.name, index === selectedIndex]"
							@click="selectCustomer(customer)"
							:class="[
								'w-full text-start p-3 rounded-lg border transition-all duration-75',
								index === selectedIndex
									? 'border-blue-500 bg-blue-50 shadow-sm'
									: 'border-gray-200 hover:border-blue-400 hover:bg-blue-50',
							]"
						>
							<div class="flex items-start justify-between">
								<div class="flex-1 min-w-0">
									<div class="font-semibold text-sm text-gray-900 truncate">
										{{ customer.customer_name }}
									</div>
									<div class="text-xs text-gray-600 mt-1 gap-2">
										<span v-if="customer.mobile_no"
											>📱 {{ customer.mobile_no }}</span
										>
										<span v-if="customer.email_id"
											>✉️ {{ customer.email_id }}</span
										>
									</div>
									<div
										v-if="customer.customer_group"
										class="text-xs text-gray-500 mt-1"
									>
										{{ customer.customer_group }}
									</div>
								</div>
								<div v-if="index === selectedIndex" class="ms-2 flex-shrink-0">
									<svg
										class="h-5 w-5 text-blue-500"
										fill="currentColor"
										viewBox="0 0 20 20"
									>
										<path
											fill-rule="evenodd"
											d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
											clip-rule="evenodd"
										/>
									</svg>
								</div>
							</div>
						</button>
					</div>
				</div>

				<!-- Create New Customer Link -->
				<div class="pt-4 border-t border-gray-200">
					<button
						@click="createNewCustomer"
						class="w-full py-2 px-4 text-sm font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition-colors"
					>
						{{ __("+ Create New Customer") }}
					</button>
				</div>
			</div>
		</template>

		<template #actions>
			<Button variant="subtle" @click="show = false">{{ __("Cancel") }}</Button>
		</template>
	</Dialog>

	<!-- Create Customer Dialog -->
	<CreateCustomerDialog
		v-model="showCreateDialog"
		:pos-profile="posProfile"
		@customer-created="handleCustomerCreated"
	/>
</template>

<script setup>
import { useCustomerSearchStore } from "@/stores/customerSearch";
import { Button, Dialog } from "frappe-ui";
import { storeToRefs } from "pinia";
import { computed, onMounted, ref, watch } from "vue";
import CreateCustomerDialog from "./CreateCustomerDialog.vue";

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
});

const emit = defineEmits(["update:modelValue", "customer-selected"]);

// Use Pinia store
const customerStore = useCustomerSearchStore();
const { filteredCustomers, loading, selectedIndex, searchTerm, allCustomers, recommendations } =
	storeToRefs(customerStore);

// Local state
const showCreateDialog = ref(false);

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
});

// Alias for template compatibility
const customers = computed(() => filteredCustomers.value);

// Show recent customers label
const showingRecent = computed(() => !searchTerm.value && customers.value.length > 0);

// Load customers when dialog opens
watch(show, (newVal) => {
	if (newVal) {
		customerStore.clearSearch();
		// loadAllCustomers will skip if already loaded (unless forceReload=true)
		customerStore.loadAllCustomers(props.posProfile);
	}
});

// Handle search input with instant reactivity
function handleSearchInput(event) {
	const value = event.target.value;
	customerStore.setSearchTerm(value);
}

// Keyboard navigation
function handleKeydown(event) {
	if (customers.value.length === 0) return;

	if (event.key === "ArrowDown") {
		event.preventDefault();
		customerStore.setSelectedIndex(
			Math.min(selectedIndex.value + 1, customers.value.length - 1),
		);
	} else if (event.key === "ArrowUp") {
		event.preventDefault();
		customerStore.setSelectedIndex(Math.max(selectedIndex.value - 1, -1));
	} else if (event.key === "Enter") {
		event.preventDefault();
		if (selectedIndex.value >= 0 && selectedIndex.value < customers.value.length) {
			selectCustomer(customers.value[selectedIndex.value]);
		} else if (customers.value.length === 1) {
			selectCustomer(customers.value[0]);
		}
	} else if (event.key === "Escape") {
		show.value = false;
	}
}

onMounted(() => {
	if (props.posProfile) {
		customerStore.loadAllCustomers(props.posProfile);
		customerStore.loadCustomerHistory();
	}
});

function selectCustomer(customer) {
	// Track selection for recommendations
	customerStore.trackCustomerSelection(customer.name);

	emit("customer-selected", customer);
	show.value = false;
}

function createNewCustomer() {
	showCreateDialog.value = true;
}

async function handleCustomerCreated(customer) {
	if (props.posProfile) {
		await customerStore.addCustomerToCache(customer);
	}

	// Track new customer selection
	customerStore.trackCustomerSelection(customer.name);

	emit("customer-selected", customer);
	show.value = false;
}
</script>

<style scoped>
.sr-only {
	position: absolute;
	width: 1px;
	height: 1px;
	padding: 0;
	margin: -1px;
	overflow: hidden;
	clip: rect(0, 0, 0, 0);
	white-space: nowrap;
	border-width: 0;
}
</style>
