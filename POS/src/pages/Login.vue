<template>
  <div class="min-h-screen flex flex-col items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
    <div class="max-w-md w-full space-y-8">
      <div class="text-center">
        <h2 class="mt-6 text-3xl font-extrabold text-gray-900">
          {{ __('Sign in to POS Next') }}
        </h2>
        <p class="mt-2 text-sm text-gray-600">
          {{ __('Access your point of sale system') }}
        </p>
      </div>

      <div class="bg-white py-8 px-6 shadow rounded-lg">
        <form class="space-y-6" @submit.prevent="submit">
          <div v-if="(runtimeConfig.isDesktop ? desktopError : session.login.error)" class="rounded-md bg-red-50 p-4">
            <div class="flex">
              <div class="flex-shrink-0">
                <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                </svg>
              </div>
              <div class="ml-3">
                <h3 class="text-sm font-medium text-red-800">
                  {{ __('Login Failed') }}
                </h3>
                <div class="mt-2 text-sm text-red-700">
                  <p v-if="runtimeConfig.isDesktop">{{ desktopError }}</p>
                  <p v-else>{{ session.login.error.messages.join('\n') }}</p>
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
              :disabled="runtimeConfig.isDesktop ? desktopLoading : session.login.loading"
            />
          </div>

          <div>
            <label class="block">
              <span class="mb-2 block text-sm leading-4 text-gray-700">{{ __('Password') }}</span>
              <div class="relative">
                <input
                  v-model="loginForm.password"
                  required
                  name="password"
                  :type="showPassword ? 'text' : 'password'"
                  :placeholder="__('Enter your password')"
                  :disabled="runtimeConfig.isDesktop ? desktopLoading : session.login.loading"
                  class="form-input block w-full border-gray-400 placeholder-gray-500 pe-10"
                />
                <button
                  type="button"
                  @click="showPassword = !showPassword"
                  class="absolute inset-y-0 end-0 flex items-center pe-3 text-gray-600 hover:text-gray-800 transition-colors focus:outline-none"
                  :disabled="runtimeConfig.isDesktop ? desktopLoading : session.login.loading"
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
              :loading="runtimeConfig.isDesktop ? desktopLoading : session.login.loading"
              variant="solid"
              class="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
              type="submit"
            >
              {{ (runtimeConfig.isDesktop ? desktopLoading : session.login.loading) ? __('Signing in...') : __('Sign in') }}
            </Button>
          </div>
        </form>
      </div>
    </div>

    <!-- Shift Opening Dialog -->
    <ShiftOpeningDialog
      v-model="showShiftDialog"
      @shift-opened="handleShiftOpened"
      @dialog-closed="handleDialogClosed"
    />
  </div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import ShiftOpeningDialog from "../components/ShiftOpeningDialog.vue"
import { session } from "../data/session"
import { useSessionLock } from "../composables/useSessionLock"
import { cleanupUserSession } from "../utils/sessionCleanup"
import { ensureCSRFToken } from "../utils/csrf"
import { offlineWorker } from "../utils/offline/workerClient"
import { logger } from "@/utils/logger"
import { runtimeConfig, getAuthHeader } from "@/utils/runtimeConfig"
import { loginAndGenerateKeys, persistApiCredentials } from "@/utils/desktopAuth"
import { userResource } from "../data/user"
import { sessionUser } from "../data/session"

const log = logger.create("Login")

const router = useRouter()
const { cachePasswordHashFromLogin } = useSessionLock()

const loginForm = reactive({
	email: "",
	password: "",
})

const showShiftDialog = ref(false)
const showPassword = ref(false)
const desktopLoading = ref(false)
const desktopError = ref(null)

// Reset state when login page mounts
onMounted(async () => {
	// Clear login form
	loginForm.email = ""
	loginForm.password = ""
	showPassword.value = false

	// Clear any login errors
	if (session.login.error) {
		session.login.reset()
	}

	// Only clear state if user is NOT logged in
	// If user is already logged in (e.g., after successful login), don't clear their session
	if (!session.isLoggedIn) {
		showShiftDialog.value = false
		await cleanupUserSession()
	}
})

async function submit() {
	if (!loginForm.email || !loginForm.password) {
		return
	}

	if (runtimeConfig.isDesktop) {
		desktopError.value = null
		desktopLoading.value = true
		try {
			const email = loginForm.email.trim()
			const { apiKey, apiSecret } = await loginAndGenerateKeys({
				email,
				password: loginForm.password,
			})
			await persistApiCredentials({ apiKey, apiSecret, userEmail: email })
			await offlineWorker.setApiConfig({
				baseUrl: runtimeConfig.baseUrl,
				authHeader: getAuthHeader(),
			})

			// Hydrate the user resource so the existing logged-in watcher fires
			if (!userResource.loading) userResource.fetch()
			await userResource.promise
			session.user = sessionUser()
			log.info("Desktop login complete", { user: session.user })
		} catch (error) {
			log.error("Desktop login failed", error)
			desktopError.value = error?.message || String(error)
		} finally {
			desktopLoading.value = false
		}
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
			if (!runtimeConfig.isDesktop) {
				// Initialize CSRF token after successful login (web only)
				try {
					log.info("User logged in, initializing CSRF token...")
					await ensureCSRFToken()

					if (window.csrf_token) {
						await offlineWorker.setCSRFToken(window.csrf_token)
					}
				} catch (error) {
					log.error("Failed to initialize CSRF token after login:", error)
				}
			}

			// Cache password hash for offline session unlock (still useful in desktop mode)
			await cachePasswordHashFromLogin(loginForm.password)

			// Show shift opening dialog after successful login
			showShiftDialog.value = true
		}
	},
)

// Watch for dialog being closed via X button (v-model update)
// When user closes dialog without action, navigate to POSSale
watch(showShiftDialog, (isOpen, wasOpen) => {
	// Only navigate if dialog was open and is now closed, and user is logged in
	if (wasOpen === true && isOpen === false && session.isLoggedIn) {
		router.push({ name: "POSSale" })
	}
})

function handleShiftOpened() {
	// Navigate to POS sale after shift is opened
	router.push({ name: "POSSale" })
}

function handleDialogClosed({ reason }) {
	// Navigate to /pos when dialog is cancelled or resumed
	// "cancelled" means user closed dialog without action
	// "resumed" means user chose to resume existing shift
	// In both cases, navigate to POSSale (existing shift will be active)
	if (reason === "cancelled" || reason === "resumed") {
		router.push({ name: "POSSale" })
	}
}

// Clear error when user starts typing
watch([() => loginForm.email, () => loginForm.password], () => {
	if (session.login.error) {
		session.login.reset()
	}
})
</script>
