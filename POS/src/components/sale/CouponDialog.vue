<template>
	<Dialog v-model="show" :options="{ title: __('Apply'), size: 'md' }">
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- Info Banner -->
				<div class="bg-blue-50 border border-blue-200 rounded-lg p-3">
					<div class="flex items-start gap-2">
						<svg
							class="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5"
							fill="currentColor"
							viewBox="0 0 20 20"
						>
							<path
								fill-rule="evenodd"
								d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
								clip-rule="evenodd"
							/>
						</svg>
						<div class="flex-1">
							<p class="text-xs font-medium text-blue-900">
								{{ __("Have a coupon code?") }}
							</p>
							<p class="text-xs text-blue-700 mt-0.5">
								{{ __("Enter your promotional or gift card code below. You can apply more than one.") }}
							</p>
						</div>
					</div>
				</div>

				<!-- Applied Coupons - one card per stacked coupon, each removable on its own -->
				<div v-if="appliedCoupons.length > 0" class="flex flex-col gap-2">
					<div class="flex items-center justify-between">
						<label class="block text-sm font-medium text-gray-700 text-start">
							{{ __("Applied Coupons ({0})", [appliedCoupons.length]) }}
						</label>
						<button
							v-if="appliedCoupons.length > 1"
							type="button"
							class="text-xs font-medium text-red-600 hover:text-red-700"
							@click="removeAllCoupons"
						>
							{{ __("Remove All") }}
						</button>
					</div>

					<div
						v-for="coupon in appliedCoupons"
						:key="coupon.code || coupon.name"
						class="bg-green-50 border-2 border-green-500 rounded-lg p-3"
					>
						<div class="flex items-center justify-between gap-3">
							<div class="flex items-center gap-2 min-w-0">
								<div
									class="w-7 h-7 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0"
								>
									<svg
										class="w-4 h-4 text-green-600"
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
								<div class="min-w-0">
									<p class="text-sm font-bold text-gray-900 truncate">
										{{ coupon.code || coupon.name }}
									</p>
									<p class="text-xs text-green-700 font-medium">
										-{{ formatCurrency(coupon.amount) }}
									</p>
								</div>
							</div>
							<button
								type="button"
								class="text-gray-400 hover:text-red-600 flex-shrink-0 p-1"
								:aria-label="__('Remove {0}', [coupon.code || coupon.name])"
								@click="removeCoupon(coupon)"
							>
								<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M6 18L18 6M6 6l12 12"
									/>
								</svg>
							</button>
						</div>
					</div>

					<!-- Combined total, only useful once 2+ coupons are stacked -->
					<div
						v-if="appliedCoupons.length > 1"
						class="flex justify-between items-center px-1 text-sm"
					>
						<span class="text-gray-600">{{ __("Total Coupon Discount") }}</span>
						<span class="font-bold text-green-600">-{{ formatCurrency(totalCouponDiscount) }}</span>
					</div>
				</div>

				<!-- Coupon Code Input - always available so more coupons can be stacked -->
				<div>
					<label class="block text-sm font-medium text-gray-700 mb-2 text-start">
						{{ appliedCoupons.length > 0 ? __("Add Another Coupon") : __("Coupon Code") }}
					</label>
					<div class="flex gap-2">
						<Input
							v-model="couponCode"
							type="text"
							:placeholder="__('ENTER-CODE-HERE')"
							class="flex-1 uppercase"
							@keyup.enter="applyCoupon"
							:disabled="applying"
						/>
						<Button
							@click="applyCoupon"
							:loading="applying"
							theme="blue"
							variant="solid"
							class="flex-shrink-0"
						>
							<svg
								class="w-3.5 h-3.5"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M5 13l4 4L19 7"
								/>
							</svg>
						</Button>
					</div>
					<p class="text-xs text-gray-500 mt-1">{{ __("Code is case-insensitive") }}</p>
				</div>

				<!-- My Gift Cards - already-applied cards are hidden from this list -->
				<div v-if="availableGiftCards.length > 0">
					<label class="block text-sm font-medium text-gray-700 mb-2 text-start">
						<div class="flex items-center gap-2">
							<svg
								class="w-4 h-4 text-purple-600"
								fill="currentColor"
								viewBox="0 0 20 20"
							>
								<path d="M4 4a2 2 0 00-2 2v1h16V6a2 2 0 00-2-2H4z" />
								<path
									fill-rule="evenodd"
									d="M18 9H2v5a2 2 0 002 2h12a2 2 0 002-2V9zM4 13a1 1 0 011-1h1a1 1 0 110 2H5a1 1 0 01-1-1zm5-1a1 1 0 100 2h1a1 1 0 100-2H9z"
									clip-rule="evenodd"
								/>
							</svg>
							<span>{{ __("My Gift Cards ({0})", [availableGiftCards.length]) }}</span>
						</div>
					</label>
					<div class="flex flex-col gap-2 max-h-60 overflow-y-auto pe-1">
						<div
							v-for="card in availableGiftCards"
							:key="card.coupon_code"
							@click="applyGiftCard(card)"
							class="bg-gradient-to-r from-purple-50 to-pink-50 border border-purple-200 rounded-lg p-3 cursor-pointer hover:shadow-md hover:border-purple-400 transition-all"
						>
							<div class="flex items-center justify-between">
								<div class="flex-1">
									<div class="flex items-center gap-2">
										<div
											class="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center"
										>
											<svg
												class="w-4 h-4 text-purple-600"
												fill="currentColor"
												viewBox="0 0 20 20"
											>
												<path
													d="M4 4a2 2 0 00-2 2v1h16V6a2 2 0 00-2-2H4z"
												/>
												<path
													fill-rule="evenodd"
													d="M18 9H2v5a2 2 0 002 2h12a2 2 0 002-2V9zM4 13a1 1 0 011-1h1a1 1 0 110 2H5a1 1 0 01-1-1zm5-1a1 1 0 100 2h1a1 1 0 100-2H9z"
													clip-rule="evenodd"
												/>
											</svg>
										</div>
										<div class="flex-1">
											<h4 class="text-sm font-bold text-gray-900">
												{{ card.coupon_code }}
											</h4>
											<p class="text-xs text-gray-600">
												{{ card.coupon_name }}
											</p>
										</div>
									</div>
								</div>
								<svg
									class="w-5 h-5 text-purple-600"
									fill="currentColor"
									viewBox="0 0 20 20"
								>
									<path
										fill-rule="evenodd"
										d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
										clip-rule="evenodd"
									/>
								</svg>
							</div>
						</div>
					</div>
				</div>

				<!-- Error Message -->
				<div v-if="errorMessage" class="bg-red-50 border border-red-200 rounded-lg p-3">
					<div class="flex items-start gap-2">
						<svg
							class="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5"
							fill="currentColor"
							viewBox="0 0 20 20"
						>
							<path
								fill-rule="evenodd"
								d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
								clip-rule="evenodd"
							/>
						</svg>
						<p class="text-xs text-red-800">{{ errorMessage }}</p>
					</div>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end w-full">
				<Button variant="subtle" @click="show = false">
					{{ __("Close") }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { DEFAULT_CURRENCY, formatCurrency as formatCurrencyUtil } from "@/utils/currency";
import { Button, Dialog, Input, createResource } from "frappe-ui";
import { computed, ref, watch } from "vue";
import { useInvoice } from "@/composables/useInvoice";
import { useToast } from "@/composables/useToast";

// Get calculateDiscountAmount helper from composable
const { calculateDiscountAmount } = useInvoice();
const { showError, showWarning } = useToast();

const props = defineProps({
	modelValue: Boolean,
	subtotal: {
		type: Number,
		required: true,
		note: __("Cart subtotal BEFORE tax - used for discount calculations"),
	},
	taxAmount: {
		type: Number,
		default: 0,
	},
	grandTotal: {
		type: Number,
		default: 0,
	},
	items: Array,
	posProfile: String,
	customer: String,
	company: String,
	currency: {
		type: String,
		default: DEFAULT_CURRENCY,
	},
	// Every coupon currently stacked on the cart. Each entry: { name, code,
	// percentage, amount, type, coupon, apply_on, base_amount }.
	appliedCoupons: {
		type: Array,
		default: () => [],
	},
});

const emit = defineEmits(["update:modelValue", "discount-applied", "discount-removed"]);

const show = ref(props.modelValue);
const couponCode = ref("");
const giftCards = ref([]);
const applying = ref(false);
const errorMessage = ref("");

// Gift cards the customer already applied shouldn't be offered again.
const availableGiftCards = computed(() => {
	const appliedCodes = new Set(
		props.appliedCoupons.map((c) => (c.code || c.name || "").toUpperCase())
	);
	return giftCards.value.filter((card) => !appliedCodes.has((card.coupon_code || "").toUpperCase()));
});

const totalCouponDiscount = computed(() =>
	props.appliedCoupons.reduce((sum, c) => sum + (Number.parseFloat(c.amount) || 0), 0)
);

// Resource to load gift cards
const giftCardsResource = createResource({
	url: "pos_next.api.offers.get_active_coupons",
	makeParams() {
		return {
			customer: props.customer,
			company: props.company,
		};
	},
	auto: false,
	onSuccess(data) {
		giftCards.value = data?.message || data || [];
	},
});

// Resource to validate coupon
const couponResource = createResource({
	url: "pos_next.api.offers.validate_coupon",
	makeParams() {
		return {
			coupon_code: couponCode.value,
			customer: props.customer,
			company: props.company,
		};
	},
	auto: false,
});

watch(
	() => props.modelValue,
	(val) => {
		show.value = val;
		if (val) {
			loadGiftCards();
			errorMessage.value = "";
			couponCode.value = "";
		}
	}
);

watch(show, (val) => {
	emit("update:modelValue", val);
});

async function loadGiftCards() {
	if (!props.customer || !props.company) return;
	try {
		await giftCardsResource.reload();
	} catch (error) {
		console.error("Error loading gift cards:", error);
	}
}

function applyGiftCard(card) {
	couponCode.value = card.coupon_code;
	applyCoupon();
}

function isAlreadyApplied(code) {
	const normalized = code.trim().toUpperCase();
	return props.appliedCoupons.some(
		(c) => (c.code || c.name || "").toUpperCase() === normalized
	);
}

function getCouponBaseAmount(coupon) {
	// Every coupon is calculated independently against the ORIGINAL
	// (undiscounted) total, not against whatever's left after previously
	// applied coupons. So "30% off + 20% off" on a 1000 bill is 300 + 200 =
	// 500 off, never 300 + 20%-of-700.
	//
	// props.grandTotal already has every currently-applied coupon's amount
	// subtracted out of it, so add that back to recover the pre-coupon
	// baseline. taxAmount is unaffected by coupons (it's computed purely
	// from item rows), so it needs no adjustment.
	const originalGrandTotal =
		Number.parseFloat(props.grandTotal || 0) + totalCouponDiscount.value;
	const taxAmount = Number.parseFloat(props.taxAmount || 0);
	const originalNetTotal = Math.max(originalGrandTotal - taxAmount, 0);

	return coupon.apply_on === "Grand Total" ? originalGrandTotal : originalNetTotal;
}

async function applyCoupon() {
	const enteredCode = couponCode.value.trim();
	if (!enteredCode) {
		errorMessage.value = __("Please enter a coupon code");
		return;
	}

	if (isAlreadyApplied(enteredCode)) {
		errorMessage.value = __("This coupon is already applied");
		showWarning(errorMessage.value);
		return;
	}

	applying.value = true;
	errorMessage.value = "";

	try {
		await couponResource.reload();
		// Frappe wraps response in { message: {...} }
		const result = couponResource.data?.message || couponResource.data;

		// Handle if result is the actual response object
		const validationData =
			typeof result === "object" && result.valid !== undefined
				? result
				: couponResource.data;

		if (!validationData || !validationData.valid) {
			errorMessage.value =
				validationData?.message || __("The coupon code you entered is not valid");
			showError(errorMessage.value);
			return;
		}

		const coupon = validationData.coupon;
		const baseAmount = getCouponBaseAmount(coupon);

		// Check minimum amount on the configured coupon base
		if (coupon.min_amount && baseAmount < coupon.min_amount) {
			errorMessage.value = __("This coupon requires a minimum purchase of ", [
				formatCurrency(coupon.min_amount),
			]);
			showWarning(errorMessage.value);
			return;
		}

		// Calculate discount on subtotal (before tax) using centralized helper
		// Transform server coupon format to discount object format
		const discountObj = {
			percentage: coupon.discount_type === "Percentage" ? coupon.discount_percentage : 0,
			amount: coupon.discount_type === "Amount" ? coupon.discount_amount : 0,
		};

		let discountAmount = calculateDiscountAmount(discountObj, baseAmount);

		// Apply maximum discount limit if specified
		if (coupon.max_amount && discountAmount > coupon.max_amount) {
			discountAmount = coupon.max_amount;
		}

		// Clamp discount to the selected coupon base to prevent negative totals
		discountAmount = Math.min(discountAmount, baseAmount);

		// Since every coupon is calculated independently against the original
		// total, stacking several large percentage coupons could otherwise add
		// up to more than the bill itself. Cap this coupon to whatever
		// headroom is left after coupons already applied, so the combined
		// discount can never exceed the original total (grand total can't go negative).
		const remainingHeadroom = Math.max(baseAmount - totalCouponDiscount.value, 0);
		discountAmount = Math.min(discountAmount, remainingHeadroom);

		const appliedDiscount = {
			name: coupon.coupon_name || coupon.coupon_code,
			code: enteredCode.toUpperCase(),
			percentage: coupon.discount_type === "Percentage" ? coupon.discount_percentage : 0,
			amount: discountAmount,
			type: coupon.discount_type,
			coupon: coupon,
			apply_on: coupon.apply_on,
			base_amount: baseAmount,
		};

		// The cart store shows the "applied successfully" toast once it
		// actually accepts the coupon (it may still reject a duplicate).
		emit("discount-applied", appliedDiscount);

		// Clear the input so the next coupon can be typed straight away, but
		// keep the dialog open so multiple coupons can be added in one go.
		couponCode.value = "";
		errorMessage.value = "";
	} catch (error) {
		console.error("Error applying coupon:", error);
		errorMessage.value = __("Failed to apply coupon. Please try again.");
		showError(errorMessage.value);
	} finally {
		applying.value = false;
	}
}

function removeCoupon(coupon) {
	emit("discount-removed", coupon);
}

function removeAllCoupons() {
	emit("discount-removed", null);
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency);
}
</script>
