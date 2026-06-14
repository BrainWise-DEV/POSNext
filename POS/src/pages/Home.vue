<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Header -->
    <header class="bg-white shadow">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
          <div class="flex items-center space-x-4">
            <h1 class="text-xl font-semibold text-gray-900">{{ __('POS Next') }}</h1>

            <!-- Shift Status Indicator -->
            <div v-if="hasOpenShift" class="flex items-center space-x-2 px-3 py-1 bg-green-100 rounded-full">
              <div class="h-2 w-2 bg-green-500 rounded-full"></div>
              <span class="text-xs font-medium text-green-700">{{ __('Shift Open') }}</span>
            </div>
          </div>

          <div class="flex items-center space-x-4">
            <!-- Shift Info -->
            <div v-if="hasOpenShift" class="text-sm text-gray-600">
              <div class="font-medium">{{ currentProfile?.name }}</div>
              <div class="text-xs text-gray-500">{{ currentCompany?.name }}</div>
            </div>

            <div class="flex items-center space-x-2">
              <div class="h-8 w-8 rounded-full bg-blue-500 flex items-center justify-center">
                <span class="text-sm font-medium text-white">
                  {{ getUserInitials(session.user) }}
                </span>
              </div>
              <span class="text-sm text-gray-700">{{ session.user }}</span>
            </div>

            <Button
              theme="gray"
              variant="subtle"
              @click="confirmLogout"
              :loading="session.logout.loading"
              class="text-gray-500 hover:text-gray-700"
            >
              {{ session.logout.loading ? __('Signing out...') : __('Sign out') }}
            </Button>
          </div>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <main class="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div class="px-4 py-6 sm:px-0">
        <div class="border-4 border-dashed border-gray-200 rounded-lg min-h-96 p-8">
          <div class="text-center">
            <h2 class="text-2xl font-bold text-gray-900 mb-4">
              {{ __('Welcome to POS Next!') }}
            </h2>
            <p class="text-gray-600 mb-8">
              {{ __('Your point of sale system is ready to use.') }}
            </p>

            <!-- Shift Management Section -->
            <div class="max-w-2xl mx-auto space-y-4">
              <!-- Shift Status Card -->
              <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-medium text-gray-900 mb-4">{{ __('Shift Status') }}</h3>

                <div v-if="hasOpenShift" class="space-y-4">
                  <div class="bg-green-50 border border-green-200 rounded-lg p-4">
                    <div class="flex items-start justify-between">
                      <div class="flex-1">
                        <div class="flex items-center space-x-2 mb-2">
                          <div class="h-3 w-3 bg-green-500 rounded-full"></div>
                          <span class="font-medium text-green-900">{{ __('Shift is Open') }}</span>
                        </div>
                        <div class="text-sm text-green-700 space-y-1">
                          <TranslatedHTML 
                            :tag="'p'"
                            :inner="__('&lt;strong&gt;POS Profile:&lt;strong&gt; {0}', [currentProfile?.name])"
                          />
                          <TranslatedHTML 
                            :tag="'p'"
                            :inner="__('&lt;strong&gt;Company:&lt;strong&gt;', [currentCompany?.name])"
                          />
                          <TranslatedHTML 
                            :tag="'p'"
                            :inner="__('&lt;strong&gt;Opened:&lt;strong&gt;', [formatDateTime(currentShift?.period_start_date)])"
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div class="flex space-x-3">
                    <Button
                      variant="solid"
                      theme="red"
                      @click="openCloseShiftDialog"
                      class="flex-1"
                    >
                      {{ __('Close Shift') }}
                    </Button>
                    <Button
                      variant="solid"
                      theme="blue"
                      @click="startSale"
                      class="flex-1"
                    >
                      {{ __('Start Sale') }}
                    </Button>
                  </div>
                </div>

                <div v-else class="space-y-4">
                  <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                    <div class="flex items-center space-x-2 mb-2">
                      <svg class="h-5 w-5 text-yellow-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
                      </svg>
                      <span class="font-medium text-yellow-900">{{ __('No Active Shift') }}</span>
                    </div>
                    <p class="text-sm text-yellow-700">
                      {{ __('You need to open a shift before you can start making sales.') }}
                    </p>
                  </div>

                  <Button
                    variant="solid"
                    theme="blue"
                    @click="showOpenShiftDialog = true"
                    class="w-full"
                  >
                    {{ __('Open Shift') }}
                  </Button>
                </div>
              </div>

              <!-- System Test -->
              <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-medium text-gray-900 mb-4">{{ __('System Test') }}</h3>
                <Button
                  theme="blue"
                  variant="solid"
                  @click="ping.fetch"
                  :loading="ping.loading"
                  class="w-full"
                >
                  {{ __('Test Connection') }}
                </Button>

                <div v-if="ping.data" class="mt-4 p-3 bg-green-50 rounded-md">
                  <div class="text-sm text-green-800">
                    {{ __('✓ Connection successful: {0}', [ping.data]) }}
                  </div>
                </div>

                <div v-if="ping.error" class="mt-4 p-3 bg-red-50 rounded-md">
                  <div class="text-sm text-red-800">
                    {{ __('✗ Connection failed: {0}', [ping.error]) }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Logout Confirmation Dialog -->
    <Dialog
      v-model="showLogoutDialog"
      :options="{ title: __('Confirm Sign Out') }"
      :dismissable="!session.logout.loading"
    >
      <template #body-content>
        <div class="space-y-4">
          <div v-if="hasOpenShift" class="rounded-md bg-yellow-50 p-4">
            <div class="flex">
              <div class="flex-shrink-0">
                <svg class="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
                </svg>
              </div>
              <div class="ml-3">
                <h3 class="text-sm font-medium text-yellow-800">
                  {{ __('Active Shift Detected') }}
                </h3>
                <div class="mt-2 text-sm text-yellow-700">
                  <p>{{ __('You have an active shift open. Would you like to:') }}</p>
                </div>
              </div>
            </div>
          </div>

          <p v-else class="text-sm text-gray-500">
            {{ __('Are you sure you want to sign out of POS Next?') }}
          </p>
        </div>
      </template>

      <template #actions>
        <div class="flex space-x-2">
          <Button
            theme="gray"
            variant="subtle"
            @click="showLogoutDialog = false"
            :disabled="session.logout.loading"
          >
            {{ __('Cancel') }}
          </Button>
          <Button
            v-if="hasOpenShift"
            theme="blue"
            variant="solid"
            @click="logoutWithCloseShift"
          >
            {{ __('Close Shift & Sign Out') }}
          </Button>
          <Button
            theme="red"
            variant="solid"
            @click="handleLogout"
            :loading="session.logout.loading"
          >
            {{ hasOpenShift ? __('Sign Out Only') : __('Sign Out') }}
          </Button>
        </div>
      </template>
    </Dialog>

    <!-- Shift Opening Dialog -->
    <ShiftOpeningDialog
      v-model="showOpenShiftDialog"
      @shift-opened="handleShiftOpened"
    />

    <!-- Shift Closing Dialog -->
    <ShiftClosingDialog
      v-model="showCloseShiftDialog"
      :opening-shift="currentShift?.name"
      @shift-closed="handleShiftClosed"
      @update:modelValue="handleCloseShiftDialogToggle"
    />
  </div>
</template>

<script setup>
import { Dialog } from "frappe-ui"
import { createResource } from "frappe-ui"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import ShiftClosingDialog from "../components/ShiftClosingDialog.vue"
import ShiftOpeningDialog from "../components/ShiftOpeningDialog.vue"
import { useShift } from "../composables/useShift"
import { session } from "../data/session"
import TranslatedHTML from "../components/common/TranslatedHTML.vue"

const router = useRouter()

const {
	hasOpenShift,
	currentShift,
	currentProfile,
	currentCompany,
	checkOpeningShift,
} = useShift()

const ping = createResource({
	url: "pos_next.api.ping",
	auto: false,
})

const showLogoutDialog = ref(false)
const showOpenShiftDialog = ref(false)
const showCloseShiftDialog = ref(false)
const logoutAfterClose = ref(false)
const closingShiftInProgress = ref(false)

onMounted(() => {
	// Check for open shift on component mount
	checkOpeningShift.fetch()
})

function getUserInitials(username) {
	if (!username) return "U"
	return username
		.split("@")[0] // Remove domain if email
		.split(" ")
		.map((name) => name[0])
		.join("")
		.toUpperCase()
		.slice(0, 2)
}

function confirmLogout() {
	showLogoutDialog.value = true
}

function handleLogout() {
	logoutAfterClose.value = false
	session.logout.submit()
}

function logoutWithCloseShift() {
	// Open close shift dialog and remember to logout after closing
	logoutAfterClose.value = true
	showLogoutDialog.value = false
	showCloseShiftDialog.value = true
}

function handleShiftOpened() {
	showOpenShiftDialog.value = false
	// Refresh shift status
	checkOpeningShift.fetch()
}

function handleShiftClosed() {
	closingShiftInProgress.value = true
	showCloseShiftDialog.value = false
	// Refresh shift status
	checkOpeningShift.fetch()
	if (logoutAfterClose.value) {
		session.logout.submit()
		logoutAfterClose.value = false
	}
	closingShiftInProgress.value = false
}

function formatDateTime(datetime) {
	if (!datetime) return ""
	return new Date(datetime).toLocaleString()
}

function openCloseShiftDialog() {
	logoutAfterClose.value = false
	showCloseShiftDialog.value = true
}

function handleCloseShiftDialogToggle(value) {
	if (!value && !closingShiftInProgress.value) {
		logoutAfterClose.value = false
	}
}

function startSale() {
	router.push({ name: "POSSale" })
}
</script>
