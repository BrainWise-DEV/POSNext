<template>
	<Dialog
		:modelValue="show"
		@update:modelValue="$emit('update:modelValue', $event)"
		:options="{
			title: __('Manager Approval Required'),
			size: 'md',
		}"
	>
		<template #body>
			<div class="space-y-4 px-2 py-2">
				<!-- Approval Details -->
				<div class="bg-blue-50 border border-blue-200 rounded-lg p-3">
					<p class="text-sm text-blue-900">
						<strong>{{ approvalType }}</strong> requires manager approval
					</p>
					<p v-if="amount > 0" class="text-lg font-bold text-blue-700 mt-2">
						{{ formatCurrency(amount) }}
					</p>
					<p v-if="reason" class="text-xs text-blue-800 mt-1">
						{{ __('Reason:') }} {{ reason }}
					</p>
				</div>

				<!-- Manager Username -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-2">
						{{ __('Manager Username') }}
					</label>
					<input
						v-model="managerUsername"
						type="text"
						:placeholder="__('Enter manager username')"
						class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
						@keyup.enter="approve"
					/>
				</div>

				<!-- Manager Password -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-2">
						{{ __('Manager Password') }}
					</label>
					<input
						v-model="managerPassword"
						type="password"
						:placeholder="__('Enter manager password')"
						class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
						@keyup.enter="approve"
					/>
				</div>

				<!-- Error Message -->
				<div v-if="errorMessage" class="bg-red-50 border border-red-200 rounded-lg p-3">
					<p class="text-sm text-red-700">{{ errorMessage }}</p>
				</div>

				<!-- Loading State -->
				<div v-if="isLoading" class="flex items-center justify-center gap-2 py-2">
					<div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
					<span class="text-sm text-gray-600">{{ __('Verifying credentials...') }}</span>
				</div>

				<div class="flex gap-2 justify-end pt-4 border-t border-gray-200">
			<button
				@click="$emit('update:modelValue', false)"
				:disabled="isLoading"
				class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
			>
				{{ __('Cancel') }}
			</button>

			<button
				@click="approve"
				:disabled="isLoading || !managerUsername || !managerPassword"
				class="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
			>
				{{ __('Approve') }}
			</button>
		</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Dialog } from 'frappe-ui'
import { call } from '@/utils/apiWrapper'
import { __ } from '@/utils/translation'
import { formatCurrency } from '@/utils/currency'

const props = defineProps({
	modelValue: Boolean,
	approvalType: {
		type: String,
		default: 'Cash Refund', // "Cash Refund" or "Discount"
	},
	amount: {
		type: Number,
		default: 0,
	},
	reason: {
		type: String,
		default: '',
	},
})

const emit = defineEmits(['update:modelValue', 'approved', 'rejected'])

const show = computed({
	get: () => props.modelValue,
	set: (val) => emit('update:modelValue', val),
})

const managerUsername = ref('')
const managerPassword = ref('')
const errorMessage = ref('')
const isLoading = ref(false)

/**
 * Verify manager credentials and emit approval
 */
async function approve() {
	if (!managerUsername.value || !managerPassword.value) {
		errorMessage.value = __('Please enter both username and password')
		return
	}

	isLoading.value = true
	errorMessage.value = ''

	try {
		// Call backend API to verify manager credentials
		const result = await call('pos_next.api.approvals.verify_manager_approval', {
			username: managerUsername.value,
			password: managerPassword.value,
			approval_type: props.approvalType,
			amount: props.amount,
		})

		if (result.success) {
			// Capture manager name before clearing
			const manager = managerUsername.value
			// Clear fields and close dialog
			managerUsername.value = ''
			managerPassword.value = ''
			emit('approved', {
				manager: manager,
				timestamp: new Date().toISOString(),
			})
			show.value = false
		} else {
			errorMessage.value = result.message || __('Invalid credentials')
		}
	} catch (error) {
		console.error('Manager approval error:', error)
		errorMessage.value = error.message || __('Error verifying credentials')
	} finally {
		isLoading.value = false
	}
}

// Reset form when dialog closes
watch(show, (newVal) => {
	if (!newVal) {
		managerUsername.value = ''
		managerPassword.value = ''
		errorMessage.value = ''
	}
})
</script>

<style scoped>
input {
	transition: all 0.2s ease;
}

input:focus {
	border-color: #3b82f6;
	box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
</style>
