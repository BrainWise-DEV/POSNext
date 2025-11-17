<template>
  <div class="min-h-screen flex bg-gray-50 relative overflow-hidden">
    <!-- Language Switcher - Fixed Top (Right for LTR, Left for RTL) -->
    <div class="fixed top-6 z-50" :class="isRTL ? 'left-6' : 'right-6'">
      <LanguageSelector />
    </div>

    <!-- Left Side - Splash Screen -->
    <div class="hidden lg:flex lg:w-1/2 xl:w-3/5 relative bg-gradient-to-br from-blue-600 via-blue-700 to-indigo-800 flex-col justify-between overflow-hidden">
      <!-- Decorative Background Elements - Positioned to highlight features -->
      <div class="absolute top-1/3 left-1/4 w-96 h-96 bg-blue-400 rounded-full mix-blend-multiply filter blur-3xl opacity-40 animate-blob"></div>
      <div class="absolute bottom-1/4 left-0 w-96 h-96 bg-indigo-500 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-blob animation-delay-2000"></div>
      <div class="absolute top-1/2 left-1/3 w-80 h-80 bg-purple-400 rounded-full mix-blend-multiply filter blur-3xl opacity-35 animate-blob animation-delay-4000"></div>

      <!-- Content -->
      <div class="relative z-10 px-12 pt-12">
        <div class="flex items-center gap-3 mb-8">
          <div class="w-12 h-12 bg-white rounded-xl flex items-center justify-center shadow-lg">
            <svg class="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
            </svg>
          </div>
          <h1 class="text-3xl font-bold text-white">{{ branding.appName }}</h1>
        </div>
      </div>

      <div class="relative z-10 px-12">
        <h2 class="text-4xl xl:text-5xl font-bold text-white leading-tight mb-6">
          {{ __(branding.tagline) }}
        </h2>
        <p class="text-xl text-blue-100 mb-12 leading-relaxed">
          {{ __(branding.subtitle) }}
        </p>

        <!-- Features -->
        <div class="space-y-4" :class="{'space-x-reverse': $isRTL && $isRTL()}">
          <div class="flex items-start gap-4 group">
            <div class="w-10 h-10 bg-white bg-opacity-20 rounded-lg flex items-center justify-center flex-shrink-0 group-hover:bg-opacity-30 transition-all duration-200">
              <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <h3 class="text-white font-semibold text-lg">{{ __("Lightning Fast") }}</h3>
              <p class="text-blue-100 text-sm">{{ __("Process transactions in seconds with optimized performance") }}</p>
            </div>
          </div>

          <div class="flex items-start gap-4 group">
            <div class="w-10 h-10 bg-white bg-opacity-20 rounded-lg flex items-center justify-center flex-shrink-0 group-hover:bg-opacity-30 transition-all duration-200">
              <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h3 class="text-white font-semibold text-lg">{{ __("Secure & Reliable") }}</h3>
              <p class="text-blue-100 text-sm">{{ __("Enterprise-grade security with offline support") }}</p>
            </div>
          </div>

          <div class="flex items-start gap-4 group">
            <div class="w-10 h-10 bg-white bg-opacity-20 rounded-lg flex items-center justify-center flex-shrink-0 group-hover:bg-opacity-30 transition-all duration-200">
              <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <div>
              <h3 class="text-white font-semibold text-lg">{{ __("Advanced Analytics") }}</h3>
              <p class="text-blue-100 text-sm">{{ __("Real-time insights and comprehensive reporting") }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer Branding -->
      <div class="relative z-10 px-12 pb-12 text-blue-100 text-sm">
        {{ branding.footerText }}
        <a :href="branding.footerLink" target="_blank" rel="noopener noreferrer" class="text-white font-semibold hover:underline ml-1">
          {{ branding.linkText }}
        </a>
      </div>
    </div>

    <!-- Right Side - Login Form -->
    <div class="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8 py-12 bg-gradient-to-br from-gray-50 to-blue-50/30">
      <div class="max-w-md w-full space-y-8">
        <!-- Mobile Logo (visible on small screens) -->
        <div class="lg:hidden text-center mb-8">
          <div class="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl shadow-lg mb-4">
            <svg class="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
            </svg>
          </div>
          <h1 class="text-2xl font-bold text-gray-900">{{ branding.appName }}</h1>
        </div>

        <div class="text-center">
          <h2 class="text-3xl font-extrabold text-gray-900">
            {{ __("Sign in to") }} {{ branding.appName }}
          </h2>
          <p class="mt-2 text-sm text-gray-600">
            {{ __("Access your point of sale system") }}
          </p>
        </div>

        <div class="bg-white py-8 px-6 shadow-2xl rounded-2xl border border-gray-200/50 backdrop-blur-sm">
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
              class="focus-within:ring-2 focus-within:ring-purple-500 focus-within:ring-opacity-50 focus-within:border-blue-600 transition-all duration-200"
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
                  class="form-input block w-full border-gray-300 placeholder-gray-500 pr-10 focus:border-blue-600 focus:ring-2 focus:ring-purple-500 focus:ring-opacity-50 transition-all duration-200"
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
              class="w-full py-2.5 px-4 border border-transparent rounded-lg shadow-md text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50 transition-all duration-200 hover:shadow-lg"
              type="submit"
            >
              {{ session.login.loading ? __('Signing in...') : __('Sign in') }}
            </Button>
          </div>
        </form>
      </div>
    </div>
    </div>

    <!-- Shift Opening Dialog -->
    <ShiftOpeningDialog
      v-model="showShiftDialog"
      @shift-opened="handleShiftOpened"
    />
  </div>
</template>

<script setup>
import { usePOSCartStore } from "@/stores/posCart"
import { usePOSUIStore } from "@/stores/posUI"
import { FeatherIcon } from "frappe-ui"
import { onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import ShiftOpeningDialog from "../components/ShiftOpeningDialog.vue"
import LanguageSelector from "../components/LanguageSelector.vue"
import { useShift } from "../composables/useShift"
import { session } from "../data/session"
import { ensureCSRFToken } from "../utils/csrf"
import { offlineWorker } from "../utils/offline/workerClient"
import { call } from "@/utils/apiWrapper"

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
const isRTL = ref(false)

// Branding configuration - all loaded from API
const branding = ref({
	appName: "",
	tagline: "",
	subtitle: "",
	footerText: "",
	linkText: "",
	footerLink: "",
})

const brandingLoaded = ref(false)

// Load branding from backend - encrypted and protected by Master Key
async function loadBranding() {
	try {
		const response = await call('pos_next.api.branding.get_login_branding')
		if (response) {
			// Decode base64 encrypted values from DocType
			// These values are protected and can only be modified with Master Key
			branding.value = {
				appName: response._an ? atob(response._an) : "",
				tagline: response._tl ? atob(response._tl) : "",
				subtitle: response._st ? atob(response._st) : "",
				footerText: response._ft ? atob(response._ft) : "",
				linkText: response._ln ? atob(response._ln) : "",
				footerLink: response._lu ? atob(response._lu) : "",
			}
			brandingLoaded.value = true

			// Log successful branding load (for security monitoring)
			console.log('[BrainWise Branding] Loaded encrypted branding configuration')
		}
	} catch (error) {
		console.error('[BrainWise Branding] Failed to load branding from DocType:', error)
		// Do not use fallbacks - branding must come from protected DocType
		brandingLoaded.value = false
	}
}

// Reset state when login page mounts
onMounted(async () => {
	// Initialize RTL support for guest users
	const guestLang = localStorage.getItem("guestLanguage")
	if (guestLang && window.$isRTL) {
		const rtlDetected = window.$isRTL(guestLang)
		isRTL.value = rtlDetected
		document.documentElement.dir = rtlDetected ? "rtl" : "ltr"
		document.documentElement.lang = guestLang
		if (rtlDetected) {
			document.body.classList.add("rtl")
		}
	}

	// Load branding configuration
	await loadBranding()

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

// Clear error when user starts typing
watch([() => loginForm.email, () => loginForm.password], () => {
	if (session.login.error) {
		session.login.reset()
	}
})
</script>

<style scoped>
@keyframes blob {
	0%, 100% {
		transform: translate(0, 0) scale(1);
	}
	25% {
		transform: translate(20px, -50px) scale(1.1);
	}
	50% {
		transform: translate(-20px, 20px) scale(0.9);
	}
	75% {
		transform: translate(50px, 50px) scale(1.05);
	}
}

.animate-blob {
	animation: blob 7s infinite;
}

.animation-delay-2000 {
	animation-delay: 2s;
}

.animation-delay-4000 {
	animation-delay: 4s;
}

/* RTL Support */
:global(.rtl) :deep(.form-input) {
	text-align: right;
}

:global(.rtl) :deep(label) {
	text-align: right;
}

/* RTL: Flip the layout - splash screen on right, form on left */
:global(.rtl) .min-h-screen.flex {
	direction: rtl;
}

/* RTL: Adjust password toggle button */
:global(.rtl) :deep(.absolute.inset-y-0.right-0) {
	right: auto;
	left: 0;
	padding-right: 0;
	padding-left: 0.75rem;
}

:global(.rtl) :deep(input) {
	padding-right: 0.75rem;
	padding-left: 2.5rem;
}
</style>
