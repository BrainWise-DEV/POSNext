<template>
	<nav
		class="px-2 sm:px-3 py-1.5 bg-white border-t border-gray-200 flex flex-wrap items-center justify-between gap-2"
		:aria-label="__('Pagination')"
	>
		<div class="text-pos-sm text-gray-600 tabular-nums">
			{{
				__("{0} - {1} of {2}", [
					(currentPage - 1) * itemsPerPage + 1,
					Math.min(currentPage * itemsPerPage, total),
					total,
				])
			}}
		</div>
		<div class="flex items-center gap-1">
			<button
				v-for="nav in startNav"
				:key="nav.key"
				type="button"
				class="pos-btn pos-btn-outline pos-btn-icon"
				:disabled="currentPage === 1"
				:aria-label="nav.label"
				:title="nav.label"
				@click="$emit('go', nav.page)"
			>
				<svg class="w-4 h-4 rtl:-scale-x-100" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="nav.icon" />
				</svg>
			</button>
			<button
				v-for="page in pageRange"
				:key="page"
				type="button"
				:class="['pos-btn tabular-nums', currentPage === page ? 'pos-btn-primary' : 'pos-btn-outline']"
				:aria-label="__('Go to page {0}', [page])"
				:aria-current="currentPage === page ? 'page' : undefined"
				@click="$emit('go', page)"
			>
				{{ page }}
			</button>
			<button
				v-for="nav in endNav"
				:key="nav.key"
				type="button"
				class="pos-btn pos-btn-outline pos-btn-icon"
				:disabled="currentPage === totalPages"
				:aria-label="nav.label"
				:title="nav.label"
				@click="$emit('go', nav.page)"
			>
				<svg class="w-4 h-4 rtl:-scale-x-100" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="nav.icon" />
				</svg>
			</button>
		</div>
	</nav>
</template>

<script setup>
import { computed } from "vue"

// Shared pager for the items grid and list. Chevrons point along the reading
// direction, so they are mirrored under RTL.
const props = defineProps({
	currentPage: { type: Number, required: true },
	totalPages: { type: Number, required: true },
	itemsPerPage: { type: Number, required: true },
	total: { type: Number, required: true },
})

defineEmits(["go"])

const startNav = computed(() => [
	{
		key: "first",
		page: 1,
		label: __("Go to first page"),
		icon: "M11 19l-7-7 7-7M19 19l-7-7 7-7",
	},
	{
		key: "prev",
		page: props.currentPage - 1,
		label: __("Go to previous page"),
		icon: "M15 19l-7-7 7-7",
	},
])

const endNav = computed(() => [
	{
		key: "next",
		page: props.currentPage + 1,
		label: __("Go to next page"),
		icon: "M9 5l7 7-7 7",
	},
	{
		key: "last",
		page: props.totalPages,
		label: __("Go to last page"),
		icon: "M13 5l7 7-7 7M5 5l7 7-7 7",
	},
])

// Every page when there are 7 or fewer, else five centred on the current page
const pageRange = computed(() => {
	const total = props.totalPages
	const first =
		total <= 7 ? 1 : Math.min(Math.max(props.currentPage - 2, 1), total - 4)
	return Array.from({ length: total <= 7 ? total : 5 }, (_, i) => first + i)
})
</script>
