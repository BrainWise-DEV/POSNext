<template>
	<div class="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-900 p-8">
		<div class="max-w-md w-full space-y-8">
			<!-- Logo/Header -->
			<div class="text-center">
				<FeatherIcon name="monitor" class="w-20 h-20 mx-auto text-blue-600 dark:text-blue-400 mb-4" />
				<h1 class="text-3xl font-bold text-gray-900 dark:text-white">{{ __("Customer Display") }}</h1>
				<p class="mt-2 text-gray-600 dark:text-gray-400">{{ __("Enter your API credentials to connect") }}</p>
			</div>

			<!-- Auth form -->
			<div class="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-2xl">
				<form class="space-y-6" @submit.prevent="handleSubmit">
					<!-- Error message -->
					<div v-if="displayStore.authError" class="p-4 bg-red-100 dark:bg-red-900/50 border border-red-300 dark:border-red-700 rounded-lg">
						<div class="flex items-start gap-3">
							<FeatherIcon name="alert-circle" class="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
							<p class="text-red-700 dark:text-red-300 text-sm">{{ displayStore.authError }}</p>
						</div>
					</div>

					<!-- API Key input -->
					<div class="space-y-2">
						<label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
							{{ __("API Key") }}
						</label>
						<div class="relative">
							<input
								v-model="apiKey"
								:type="showKey ? 'text' : 'password'"
								:placeholder="__('api_key:api_secret')"
								class="w-full px-4 py-3 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
								:disabled="displayStore.isLoading"
								required
							/>
							<button
								type="button"
								class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
								@click="showKey = !showKey"
							>
								<FeatherIcon :name="showKey ? 'eye-off' : 'eye'" class="w-5 h-5" />
							</button>
						</div>
						<p class="text-xs text-gray-500">
							{{ __("Format: api_key:api_secret") }}
						</p>
					</div>

					<!-- Help text -->
					<div class="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
						<h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
							{{ __("How to get your API key") }}
						</h3>
						<ol class="text-xs text-gray-600 dark:text-gray-400 space-y-1 list-decimal list-inside">
							<li>{{ __("Go to User Settings in Frappe") }}</li>
							<li>{{ __("Navigate to API Access section") }}</li>
							<li>{{ __("Generate new API key if needed") }}</li>
							<li>{{ __("Copy both api_key and api_secret") }}</li>
						</ol>
					</div>

					<!-- Submit button -->
					<button
						type="submit"
						:disabled="displayStore.isLoading || !apiKey"
						class="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-medium text-white transition-colors flex items-center justify-center gap-2"
					>
						<FeatherIcon
							v-if="displayStore.isLoading"
							name="loader"
							class="w-5 h-5 animate-spin"
						/>
						<span>{{ displayStore.isLoading ? __("Connecting...") : __("Connect") }}</span>
					</button>
				</form>
			</div>

			<!-- Footer -->
			<p class="text-center text-gray-500 text-sm">
				{{ __("POS Next Customer Display") }}
			</p>
		</div>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { ref } from "vue"
import { useCustomerDisplayStore } from "@/stores/customerDisplay"

const displayStore = useCustomerDisplayStore()

const apiKey = ref("")
const showKey = ref(false)

async function handleSubmit() {
	if (!apiKey.value) return

	const success = await displayStore.authenticate(apiKey.value)
	if (success) {
		// Clear the input for security
		apiKey.value = ""
	}
}
</script>
