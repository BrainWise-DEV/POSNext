<template>
  <div class="min-h-screen flex flex-col items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
    <div class="max-w-md w-full space-y-8">
      <div class="text-center">
        <h2 class="mt-6 text-3xl font-extrabold text-gray-900">
          {{ __("Sign in to POS Next") }}
        </h2>
        <p class="mt-2 text-sm text-gray-600">
          {{ __("Access your point of sale system") }}
        </p>
      </div>

      <div class="bg-white py-8 px-6 shadow rounded-lg">
        <form class="space-y-6" @submit.prevent="submit">
          <div v-if="session.login.error" class="rounded-md bg-red-50 p-4">
            <div class="flex">
              <div class="flex-shrink-0">
                <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                </svg>
              </div>
              <div class="ml-3">
                <h3 class="text-sm font-medium text-red-800">
                  {{ __("Login Failed") }}
                </h3>
                <div class="mt-2 text-sm text-red-700">
                  <p>{{ session.login.error }}</p>
                </div>
              </div>
            </div>
          </div>

          <div>
            <Input
              v-model="loginForm.email"
              required
              name="email"
              type="text"
              :placeholder="__('Enter your username or email')"
              :label="__('User ID / Email')"
              :disabled="session.login.loading"
            />
          </div>

          <div>
            <label class="block">
              <span class="mb-2 block text-sm leading-4 text-gray-700">{{ __("Password") }}</span>
              <div class="relative">
                <input
                  v-model="loginForm.password"
                  required
                  name="password"
                  :type="showPassword ? 'text' : 'password'"
                  :placeholder="__('Enter your password')"
                  :disabled="session.login.loading"
                  class="form-input block w-full border-gray-400 placeholder-gray-500 pr-10"
                />
                <button
                  type="button"
                  @click="showPassword = !showPassword"
                  class="absolute inset-y-0 right-0 flex items-center pr-3 text-gray-600 hover:text-gray-800 transition-colors focus:outline-none"
                  :disabled="session.login.loading"
                  tabindex="-1"
                  :aria-label="showPassword ? __('Hide password') : __('Show password')"
                >
                  <FeatherIcon
                    :name="showPassword ? 'eye-off' : 'eye'"
                    class="h-5 w-5"
                    :stroke-width="2"
                  />
                </button>
              </div>
            </label>
          </div>

          <div>
            <Button
              :loading="session.login.loading"
              variant="solid"
              class="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
              type="submit"
            >
              {{ session.login.loading ? __('Signing in...') : __('Sign in') }}
            </Button>
          </div>
        </form>
      </div>
    </div>

    <!-- Shift Opening Dialog -->
    <ShiftOpeningDialog
      v-model="showShiftDialog"
      @shift-opened="handleShiftOpened"
    />

    <!-- Language Switcher Footer -->
    <div class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 py-3 px-4">
      <div class="max-w-md mx-auto flex items-center justify-center gap-2">
        <svg class="h-5 w-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
        </svg>
        <select
          v-model="selectedLanguage"
          @change="handleLanguageChange"
          class="form-select text-sm border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
        >
          <option v-for="lang in availableLanguages" :key="lang.language_code" :value="lang.language_code">
            {{ lang.language_name }}
          </option>
        </select>
      </div>
    </div>
  </div>
</template>

<script setup>
import { usePOSCartStore } from "@/stores/posCart"
import { usePOSUIStore } from "@/stores/posUI"
import { createResource, FeatherIcon } from "frappe-ui"
import { onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import ShiftOpeningDialog from "../components/ShiftOpeningDialog.vue"
import { useShift } from "../composables/useShift"
import { session } from "../data/session"
import { ensureCSRFToken } from "../utils/csrf"
import { offlineWorker } from "../utils/offline/workerClient"

const router = useRouter()
const { shiftState } = useShift()
const cartStore = usePOSCartStore()
const uiStore = usePOSUIStore()

const loginForm = reactive({
	email: "",
	password: "",
})

const showShiftDialog = ref(false)
const showPassword = ref(false)
const availableLanguages = ref([])
const selectedLanguage = ref(localStorage.getItem("preferredLanguage") || "en")

// Fetch available languages
const languagesResource = createResource({
	url: "pos_next.api.get_available_languages",
	auto: true,
	onSuccess(data) {
		availableLanguages.value = data
	},
})

// Reset state when login page mounts
onMounted(() => {
	// Clear login form
	loginForm.email = ""
	loginForm.password = ""
	showPassword.value = false
	showShiftDialog.value = false

	// Clear any login errors
	if (session.login.error) {
		session.login.reset()
	}

	// Clear cart and UI state to ensure clean slate
	cartStore.clearCart()
	uiStore.resetAllDialogs()

	// Clear any stale shift state
	shiftState.value = {
		pos_opening_shift: null,
		pos_profile: null,
		company: null,
		isOpen: false,
	}
	localStorage.removeItem("pos_shift_data")

	// Set initial RTL direction based on stored language
	const language = localStorage.getItem("preferredLanguage") || "en"
	const rtlLanguages = ["ar", "he", "fa", "ur"]
	document.documentElement.dir = rtlLanguages.includes(language) ? "rtl" : "ltr"
	document.documentElement.lang = language
})

function submit() {
	if (!loginForm.email || !loginForm.password) {
		return
	}

	session.login.submit({
		email: loginForm.email.trim(),
		password: loginForm.password,
	})
}

// Watch for successful login
watch(
	() => session.isLoggedIn,
	async (isLoggedIn) => {
		if (isLoggedIn) {
			// Initialize CSRF token after successful login
			try {
				console.log("User logged in, initializing CSRF token...")
				await ensureCSRFToken()

				// Sync CSRF token to worker for background API calls
				if (window.csrf_token) {
					await offlineWorker.setCSRFToken(window.csrf_token)
				}
			} catch (error) {
				console.error("Failed to initialize CSRF token after login:", error)
			}

			// Show shift opening dialog after successful login
			showShiftDialog.value = true
		}
	},
)

function handleShiftOpened() {
	// Navigate to POS sale after shift is opened
	router.push({ name: "POSSale" })
}

// Handle language change
async function handleLanguageChange() {
	const language = selectedLanguage.value
	if (!language) return

	// Store preference
	localStorage.setItem("preferredLanguage", language)

	// Set document direction for RTL languages
	const rtlLanguages = ["ar", "he", "fa", "ur"]
	document.documentElement.dir = rtlLanguages.includes(language) ? "rtl" : "ltr"
	document.documentElement.lang = language

	// Fetch new translations
	try {
		const translationsResource = createResource({
			url: "pos_next.api.get_translations",
			params: { language },
		})
		await translationsResource.fetch()
		window.translatedMessages = translationsResource.data

		// Force page reload to apply translations
		window.location.reload()
	} catch (error) {
		console.error("Failed to load translations:", error)
	}
}

// Clear error when user starts typing
watch([() => loginForm.email, () => loginForm.password], () => {
	if (session.login.error) {
		session.login.reset()
	}
})
</script>
