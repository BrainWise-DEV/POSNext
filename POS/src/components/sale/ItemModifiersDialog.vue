<template>
	<Dialog
		v-model="show"
		:options="{
			title: __('Special Instructions'),
			size: 'md',
		}"
	>
		<template #body-content>
			<div class="p-4 space-y-4">
				<div v-if="item" class="flex items-center space-x-3 mb-4 p-3 bg-gray-50 rounded-lg">
					<div class="flex-1 min-w-0">
						<p class="text-sm font-bold text-gray-900 truncate">{{ item.item_name }}</p>
						<p class="text-xs text-gray-500">{{ item.item_code }}</p>
					</div>
					<div class="text-sm font-medium">{{ item.quantity }} {{ item.uom }}</div>
				</div>

				<div>
					<label class="block text-sm font-medium text-gray-700 mb-2">{{ __("Quick Modifiers") }}</label>
					<div class="flex flex-wrap gap-2">
						<button
							v-for="mod in quickModifiers"
							:key="mod"
							@click="appendModifier(mod)"
							class="px-3 py-1.5 text-xs font-medium bg-white border border-gray-300 rounded-md hover:bg-gray-50 hover:border-blue-300 transition-colors"
						>
							{{ __(mod) }}
						</button>
					</div>
				</div>

				<div>
					<label class="block text-sm font-medium text-gray-700 mb-2">{{ __("Custom Instructions") }}</label>
					<textarea
						v-model="instructions"
						rows="4"
						class="w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm resize-none"
						:placeholder="__('Enter any special requests or dietary requirements...')"
					></textarea>
				</div>
			</div>
		</template>

		<template #actions>
			<div class="flex justify-end gap-2 w-full mt-4">
				<Button @click="show = false" variant="subtle">
					{{ __("Cancel") }}
				</Button>
				<Button @click="saveInstructions" variant="solid" theme="blue">
					{{ __("Save Instructions") }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch } from "vue"
import { Dialog, Button } from "frappe-ui"
import { usePOSCartStore } from "@/stores/posCart"

const show = ref(false)
const item = ref(null)
const instructions = ref("")
const cartStore = usePOSCartStore()

// Default quick modifiers - could be fetched from settings later
const quickModifiers = [
	"No Onion",
	"Extra Spicy",
	"Mild",
	"No Tomato",
	"Extra Cheese",
	"Takeaway",
	"Dine-in"
]

const open = (cartItem) => {
	item.value = cartItem
	instructions.value = cartItem.posa_special_instructions || ""
	show.value = true
}

const appendModifier = (mod) => {
	if (instructions.value) {
		instructions.value += `, ${mod}`
	} else {
		instructions.value = mod
	}
}

const saveInstructions = () => {
	if (item.value) {
		cartStore.updateItemInstructions(item.value.item_code, item.value.uom, instructions.value)
	}
	show.value = false
}

defineExpose({ open })
</script>
