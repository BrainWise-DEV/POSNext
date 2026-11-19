/**
 * @vitest-environment jsdom
 */
import { mount, flushPromises } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const showSuccess = vi.fn()
const showError = vi.fn()
const handleError = vi.fn((error, fallback) => {
	const message =
		(Array.isArray(error?.messages) && error.messages[0]) ||
		error?.message ||
		fallback
	showError(message)
})
const canCreateCustomer = vi.fn(async () => true)
const resourceConfigs = []

vi.mock("frappe-ui", () => ({
	Button: {
		name: "Button",
		inheritAttrs: false,
		template: `<button type="button" v-bind="$attrs" @click="$emit('click')"><slot /></button>`,
	},
	Input: {
		name: "Input",
		props: ["modelValue"],
		template: `<input :value="modelValue" />`,
	},
	Dialog: {
		name: "Dialog",
		props: ["modelValue", "options"],
		template: `<div class="dialog-stub"><slot /><slot name="body-content" /><slot name="actions" /></div>`,
	},
	createResource: (opts) => {
		const resource = {
			loading: false,
			data: null,
			submit: vi.fn(),
			reload: vi.fn(),
			fetch: vi.fn(async () => {
				if (opts.url === "frappe.geo.country_info.get_country_timezone_info") {
					opts.onSuccess({
						country_info: {
							Egypt: { code: "eg", isd: "+20" },
							Australia: { code: "au", isd: "+61" },
							"Heard Island and McDonald Islands": { code: "hm", isd: "+0" },
						},
					})
				}
			}),
		}
		resourceConfigs.push({ opts, resource })
		return resource
	},
}))

vi.mock("@/composables/usePermissions", () => ({
	usePOSPermissions: () => ({ canCreateCustomer }),
}))

vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess, showError, handleError }),
}))

const posSettings = {
	customerEmailVerificationEnabled: false,
	requireSplitName: false,
	placeholderEmailDomain: "",
}
const canOffer = vi.fn(() => false)
const panelSend = vi.fn()

vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => posSettings,
}))

vi.mock("@/stores/posShift", () => ({
	usePOSShiftStore: () => ({
		currentProfile: { country: "Egypt" },
	}),
}))

vi.mock("@/stores/bootstrap", () => ({
	useBootstrapStore: () => ({
		getPreloadedPOSProfile: () => ({ country: "Egypt" }),
	}),
}))

vi.mock("@/stores/customerSearch", () => ({
	useCustomerSearchStore: () => ({
		addCustomerToCache: vi.fn(),
	}),
}))

vi.mock("@/utils/offline/offlineState", () => ({
	isOffline: () => false,
}))

vi.mock("@/utils/customerVerification", () => ({
	canOfferEmailVerification: (...a) => canOffer(...a),
	fetchFnfMembership: vi.fn(async () => false),
	fetchVerificationStatus: vi.fn(),
}))

vi.mock("@/utils/logger", () => ({
	logger: { create: () => ({ info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() }) },
}))

vi.mock("@/components/sale/EmailVerificationPanel.vue", () => ({
	default: {
		name: "EmailVerificationPanel",
		props: ["customer", "email", "savedEmail"],
		emits: ["save-and-send"],
		setup(_, { expose }) {
			expose({ send: (...a) => panelSend(...a) })
		},
		template: '<div data-testid="panel-stub" />',
	},
}))

import CreateCustomerDialog from "../CreateCustomerDialog.vue"

const t = (s, args) => (args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s)
globalThis.__ = t

async function openEditor(mobile_no) {
	setActivePinia(createPinia())
	const wrapper = mount(CreateCustomerDialog, {
		props: {
			modelValue: false,
			posProfile: "POS-A",
			customer: { name: "Walk-In Customer", customer_name: "Walk-In Customer", mobile_no },
		},
		global: { mocks: { __: t } },
	})
	await wrapper.setProps({ modelValue: true })
	await flushPromises()
	return wrapper
}

const button = (wrapper) => wrapper.find('[data-testid="country-code-button"]')

describe("CreateCustomerDialog default country for a bogus stored ISD", () => {
	beforeEach(() => {
		resourceConfigs.length = 0
	})
	afterEach(() => {
		document.body.innerHTML = ""
	})

	it("shows the profile country (Egypt, +20) for Walk-In's +0000000000", async () => {
		const wrapper = await openEditor("+0000000000")
		expect(button(wrapper).text()).toContain("+20")
		expect(button(wrapper).text()).not.toContain("+0")
		expect(button(wrapper).find("img").attributes("src")).toContain("/eg.png")
		wrapper.unmount()
	})

	it("keeps a real stored ISD instead of the profile country", async () => {
		const wrapper = await openEditor("+61-412345678")
		expect(button(wrapper).text()).toContain("+61")
		wrapper.unmount()
	})

	it("parses a legacy number without the dash", async () => {
		const wrapper = await openEditor("+201012345678")
		expect(button(wrapper).text()).toContain("+20")
		wrapper.unmount()
	})
})
