<template>
	<div
		v-if="state.open"
		class="pointer-events-auto fixed inset-0 z-[var(--z-authorization)] flex items-center justify-center bg-black/50 p-4"
		@click.self="onCancel"
		@pointerdown.stop
	>
		<FocusScope trapped as-child>
			<div class="w-full max-w-sm rounded-xl bg-white shadow-xl dark:bg-gray-800">
				<div class="border-b border-gray-200 px-5 py-4 dark:border-gray-700">
					<h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
						{{ __("Authorization Required") }}
					</h3>
					<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
						{{ __("A manager must approve this action.") }}
					</p>
				</div>

				<div class="space-y-4 px-5 py-4">
					<div v-if="loading" class="py-6 text-center text-sm text-gray-500">
						{{ __("Loading approvers…") }}
					</div>

					<div
						v-else-if="!authorizers.length"
						class="rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-900/30 dark:text-amber-200"
					>
						{{
							__(
								"No approver is available. Ask a System Manager to set an authorization PIN for a manager."
							)
						}}
					</div>

					<template v-else>
						<div>
							<label
								class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
							>
								{{ __("Approver") }}
							</label>
							<select
								v-model="approver"
								class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
							>
								<option
									v-for="person in authorizers"
									:key="person.user"
									:value="person.user"
								>
									{{ person.full_name || person.user }}
								</option>
							</select>
						</div>

						<div>
							<label
								class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
							>
								{{ __("PIN") }}
							</label>
							<input
								ref="pinInput"
								v-model="pin"
								type="password"
								inputmode="numeric"
								autocomplete="off"
								:maxlength="pinLength"
								:placeholder="__('{0}-digit PIN', [pinLength])"
								class="w-full rounded-lg border px-3 py-2 text-center text-2xl tracking-[0.5em] dark:bg-gray-700 dark:text-gray-100"
								:class="
									errorMessage
										? 'border-red-500'
										: 'border-gray-300 dark:border-gray-600'
								"
								@keyup.enter="onApprove"
							/>
							<p v-if="errorMessage" class="mt-1.5 text-sm text-red-600">
								{{ errorMessage }}
							</p>
						</div>
					</template>
				</div>

				<div
					class="flex justify-end gap-2 border-t border-gray-200 px-5 py-3 dark:border-gray-700"
				>
					<button
						type="button"
						class="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
						@click="onCancel"
					>
						{{ __("Cancel") }}
					</button>
					<button
						type="button"
						:disabled="!canApprove"
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
						@click="onApprove"
					>
						{{ verifying ? __("Verifying…") : __("Approve") }}
					</button>
				</div>
			</div>
		</FocusScope>
	</div>
</template>

<script setup>
import { useAuthorizationDialog } from "@/composables/useAuthorization";
import { computed, nextTick, ref, watch } from "vue";
import { FocusScope } from "reka-ui";

const {
	state,
	loadAuthorizers,
	requestGrant,
	pinLength: getPinLength,
	approve,
	cancel,
} = useAuthorizationDialog();

const authorizers = ref([]);
const approver = ref("");
const pin = ref("");
const errorMessage = ref("");
const loading = ref(false);
const verifying = ref(false);
const pinInput = ref(null);
const pinLength = ref(getPinLength());

const canApprove = computed(
	() => Boolean(approver.value) && pin.value.length === pinLength.value && !verifying.value
);

watch(
	() => state.open,
	async (open) => {
		if (!open) return;

		authorizers.value = [];
		approver.value = "";
		pin.value = "";
		pinLength.value = getPinLength();
		errorMessage.value = "";
		loading.value = true;

		authorizers.value = await loadAuthorizers();
		if (authorizers.value.length) {
			approver.value = authorizers.value[0].user;
		}
		loading.value = false;

		await nextTick();
		pinInput.value?.focus();
	}
);

async function onApprove() {
	if (!canApprove.value) return;

	verifying.value = true;
	errorMessage.value = "";

	try {
		const result = await requestGrant(approver.value, pin.value);
		if (result?.authorized) {
			approve(result);
			return;
		}
		errorMessage.value = result?.message || __("Authorization failed");
	} catch (error) {
		errorMessage.value = error?.message || __("Authorization failed");
	} finally {
		verifying.value = false;
		pin.value = "";
		await nextTick();
		pinInput.value?.focus();
	}
}

function onCancel() {
	cancel();
}
</script>
