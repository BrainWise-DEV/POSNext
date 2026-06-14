<template>
	<div class="phone-input-container">
		<label v-if="label" class="block text-sm font-medium text-gray-700 mb-2">
			{{ label }}
			<span v-if="required" class="text-red-500">*</span>
		</label>

		<div class="flex">
			<!-- Country Code Selector -->
			<CountryCodeSelector
				v-model="countryISD"
				:disabled="disabled"
				:default-country="defaultCountry"
				@country-change="handleCountryChange"
			/>

			<!-- Phone Number Input -->
			<input
				v-model="phoneNumber"
				type="tel"
				:placeholder="placeholder"
				:disabled="disabled"
				:required="required"
				class="flex-1 px-3 py-2 border border-s-0 border-gray-300 rounded-r-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
				:class="{
					'border-red-300 focus:ring-red-500': !isValid && phoneNumber,
					'bg-gray-50': disabled,
				}"
				@input="handleInput"
				@blur="handleBlur"
			/>
		</div>

		<!-- Validation Error Message -->
		<p v-if="!isValid && phoneNumber && showError" class="mt-1 text-sm text-red-600">
			{{ errorMessage }}
		</p>

		<!-- Helper Text -->
		<p v-else-if="helperText" class="mt-1 text-sm text-gray-500">
			{{ helperText }}
		</p>
	</div>
</template>

<script setup>
import CountryCodeSelector from "./CountryCodeSelector.vue"
import { useCountryCodes } from "@/composables/useCountryCodes"
import { computed, ref, watch, onMounted } from "vue"

const props = defineProps({
	modelValue: {
		type: String,
		default: "",
	},
	label: {
		type: String,
		default: "",
	},
	placeholder: {
		type: String,
		default: "Enter phone number",
	},
	required: {
		type: Boolean,
		default: false,
	},
	disabled: {
		type: Boolean,
		default: false,
	},
	defaultCountry: {
		type: String,
		default: "United States",
	},
	helperText: {
		type: String,
		default: "",
	},
	validateOnBlur: {
		type: Boolean,
		default: true,
	},
})

const emit = defineEmits(["update:modelValue", "validate"])

const { parsePhoneNumber, formatPhoneNumber, validatePhoneNumber } = useCountryCodes()

const countryISD = ref("")
const phoneNumber = ref("")
const showError = ref(false)
const currentCountry = ref(null)

// Validation
const isValid = computed(() => {
	if (!phoneNumber.value) return true // Empty is valid unless required
	return validatePhoneNumber(phoneNumber.value)
})

const errorMessage = computed(() => {
	if (!phoneNumber.value) return ""
	if (!isValid.value) {
		return "Please enter a valid phone number (7-15 digits)"
	}
	return ""
})

// Handle country change
function handleCountryChange(country) {
	currentCountry.value = country
	updateFullValue()
}

// Handle input
function handleInput() {
	// Only allow digits, spaces, hyphens, parentheses
	phoneNumber.value = phoneNumber.value.replace(/[^\d\s\-\(\)]/g, "")
	showError.value = false
	updateFullValue()
}

// Handle blur
function handleBlur() {
	if (props.validateOnBlur) {
		showError.value = !isValid.value && !!phoneNumber.value
		emit("validate", isValid.value)
	}
}

// Update full value (ISD-NUMBER format)
function updateFullValue() {
	const fullValue = formatPhoneNumber(countryISD.value, phoneNumber.value)
	emit("update:modelValue", fullValue)
}

// Parse incoming value
function parseIncomingValue(value) {
	if (!value) {
		countryISD.value = ""
		phoneNumber.value = ""
		return
	}

	const parsed = parsePhoneNumber(value)
	if (parsed.isd) {
		countryISD.value = parsed.isd
		phoneNumber.value = parsed.number
	} else {
		phoneNumber.value = value
	}
}

// Watch for external value changes
watch(
	() => props.modelValue,
	(newValue, oldValue) => {
		// Only parse if value changed externally (not from our own update)
		const currentFullValue = formatPhoneNumber(countryISD.value, phoneNumber.value)
		if (newValue !== currentFullValue) {
			parseIncomingValue(newValue)
		}
	}
)

// Initialize
onMounted(() => {
	if (props.modelValue) {
		parseIncomingValue(props.modelValue)
	}
})
</script>

<style scoped>
/* Remove spinner arrows from number input */
input[type="tel"]::-webkit-outer-spin-button,
input[type="tel"]::-webkit-inner-spin-button {
	-webkit-appearance: none;
	margin: 0;
}

input[type="tel"] {
	-moz-appearance: textfield;
}
</style>
