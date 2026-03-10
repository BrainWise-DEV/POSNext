<template>
	<div class="flex-shrink-0 w-80 lg:w-96 bg-white dark:bg-gray-800 rounded-xl shadow-md border overflow-hidden flex flex-col h-full"
		:class="{
			'border-yellow-300': order.kds_status === 'Pending',
			'border-blue-400': order.kds_status === 'Preparing',
			'border-green-500': order.kds_status === 'Ready'
		}">

		<!-- Card Header -->
		<div class="px-4 py-3 border-b flex justify-between items-center"
			:class="{
				'bg-yellow-50 dark:bg-yellow-900/30': order.kds_status === 'Pending',
				'bg-blue-50 dark:bg-blue-900/30': order.kds_status === 'Preparing',
				'bg-green-50 dark:bg-green-900/30': order.kds_status === 'Ready'
			}">
			<div>
				<h3 class="font-bold text-lg leading-tight">{{ order.restaurant_table }}</h3>
				<span class="text-xs text-gray-500 font-medium">#{{ order.name.substring(0,8) }}</span>
			</div>

			<div class="text-right">
				<div class="font-mono text-xl font-bold" :class="timeColorClass">
					{{ elapsedTime }}
				</div>
				<span class="text-[10px] uppercase font-bold tracking-wider rounded-full px-2 py-0.5"
					:class="{
						'bg-yellow-200 text-yellow-800': order.kds_status === 'Pending',
						'bg-blue-200 text-blue-800': order.kds_status === 'Preparing',
						'bg-green-200 text-green-800': order.kds_status === 'Ready'
					}">
					{{ __(order.kds_status) }}
				</span>
			</div>
		</div>

		<!-- Order Items -->
		<div class="flex-1 overflow-y-auto p-4 bg-white dark:bg-gray-800">
			<ul class="divide-y divide-gray-100 dark:divide-gray-700">
				<li v-for="item in order.items" :key="item.item_code" class="py-3 flex justify-between items-start">
					<div class="flex-1 pr-4">
						<div class="font-medium text-gray-900 dark:text-gray-100 leading-tight">
							{{ item.item_name }}
						</div>
						<div v-if="item.description && item.description !== item.item_name" class="text-xs text-gray-500 mt-1 line-clamp-2">
							{{ item.description }}
						</div>
						<div v-if="item.posa_special_instructions" class="mt-2 text-xs font-bold text-blue-700 bg-blue-50 dark:text-blue-300 dark:bg-blue-900/30 p-2 rounded border border-blue-100 dark:border-blue-800 inline-block">
							{{ item.posa_special_instructions }}
						</div>
					</div>
					<div class="font-bold text-lg w-8 h-8 flex items-center justify-center rounded-lg bg-gray-100 dark:bg-gray-700">
						{{ item.qty }}
					</div>
				</li>
			</ul>
		</div>

		<!-- Action Buttons -->
		<div class="p-3 border-t bg-gray-50 dark:bg-gray-800/80">
			<Button
				v-if="order.kds_status === 'Pending'"
				variant="solid"
				class="w-full h-12 text-base font-bold bg-blue-600 hover:bg-blue-700 text-white shadow-md"
				@click="updateStatus('Preparing')"
				:loading="loading"
			>
				<template #prefix><svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg></template>
				{{ __("Start Preparing") }}
			</Button>

			<Button
				v-if="order.kds_status === 'Preparing'"
				variant="solid"
				class="w-full h-12 text-base font-bold bg-green-500 hover:bg-green-600 text-white shadow-md"
				@click="updateStatus('Ready')"
				:loading="loading"
			>
				<template #prefix><svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg></template>
				{{ __("Mark Ready") }}
			</Button>

			<Button
				v-if="order.kds_status === 'Ready'"
				variant="outline"
				class="w-full h-12 text-base font-bold border-2 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
				@click="updateStatus('Delivered')"
				:loading="loading"
			>
				<template #prefix><svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg></template>
				{{ __("Delivered / Dismiss") }}
			</Button>
		</div>
	</div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue"
import { Button } from "frappe-ui"
import { call } from "@/utils/apiWrapper"
import { useToast } from "@/composables/useToast"

const props = defineProps({
	order: {
		type: Object,
		required: true
	}
})

const emit = defineEmits(["status-updated"])
const { showError } = useToast()
const loading = ref(false)

const now = ref(new Date())
let timerInterval = null

// Timer Logic
onMounted(() => {
	timerInterval = setInterval(() => {
		now.value = new Date()
	}, 1000)
})

onUnmounted(() => {
	if (timerInterval) clearInterval(timerInterval)
})

const orderTime = computed(() => new Date(props.order.creation))
const elapsedMinutes = computed(() => Math.floor((now.value - orderTime.value) / 60000))
const elapsedSeconds = computed(() => Math.floor(((now.value - orderTime.value) % 60000) / 1000))

const elapsedTime = computed(() => {
	const min = elapsedMinutes.value.toString().padStart(2, '0')
	const sec = elapsedSeconds.value.toString().padStart(2, '0')
	return `${min}:${sec}`
})

const timeColorClass = computed(() => {
	if (props.order.kds_status === 'Ready') return 'text-green-600'
	if (elapsedMinutes.value > 15) return 'text-red-600 animate-pulse'
	if (elapsedMinutes.value > 10) return 'text-orange-500'
	return 'text-gray-800 dark:text-gray-200'
})

async function updateStatus(newStatus) {
	loading.value = true
	try {
		const res = await call("pos_next.api.restaurant.update_kds_status", {
			invoice_name: props.order.name,
			status: newStatus
		})

		if (res && res.status === 'success') {
			emit("status-updated")
		}
	} catch (error) {
		console.error("Failed to update status:", error)
		showError(__("Failed to update KDS order status."))
	} finally {
		loading.value = false
	}
}
</script>
