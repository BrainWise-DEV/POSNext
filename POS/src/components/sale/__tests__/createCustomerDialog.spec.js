/**
 * @vitest-environment jsdom
 */
import { mount, flushPromises } from "@vue/test-utils"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const showSuccess = vi.fn()
const showError = vi.fn()
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
		template: `<input />`,
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
		}
		resourceConfigs.push({ opts, resource })
		return resource
	},
}))

vi.mock("@/composables/usePermissions", () => ({
	usePOSPermissions: () => ({ canCreateCustomer }),
}))

vi.mock("@/composables/useToast", () => ({
	useToast: () => ({ showSuccess, showError }),
}))

vi.mock("@/stores/countries", () => ({
	useCountriesStore: () => ({
		countries: [{ isd: "+964", name: "Iraq", code: "IQ" }],
		countryNameToISDMap: { Iraq: "+964" },
		parsePhoneNumber: () => ({ isd: "+964", number: "7754539344" }),
		findCountryByCode: () => ({ isd: "+964", name: "Iraq", code: "IQ" }),
		findCountryByISD: () => ({ isd: "+964", name: "Iraq", code: "IQ" }),
		loadCountries: vi.fn(async () => {}),
	}),
}))

vi.mock("@/stores/posSettings", () => ({
	usePOSSettingsStore: () => ({
		customerEmailVerificationEnabled: false,
		miraayaInstalled: false,
	}),
}))

vi.mock("@/stores/posShift", () => ({
	usePOSShiftStore: () => ({
		currentProfile: { country: "Iraq" },
	}),
}))

vi.mock("@/stores/bootstrap", () => ({
	useBootstrapStore: () => ({
		getPreloadedPOSProfile: () => ({ country: "Iraq" }),
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
	canOfferEmailVerification: () => false,
	fetchFnfMembership: vi.fn(async () => false),
	fetchVerificationStatus: vi.fn(),
}))

vi.mock("@/utils/logger", () => ({
	logger: { create: () => ({ info: vi.fn(), error: vi.fn(), warn: vi.fn(), debug: vi.fn() }) },
}))

vi.mock("@/components/sale/EmailVerificationPanel.vue", () => ({
	default: { name: "EmailVerificationPanel", template: "<div />" },
}))

import CreateCustomerDialog from "../CreateCustomerDialog.vue"

const t = (s, args) => (args ? s.replace(/\{(\d+)\}/g, (_, i) => args[i]) : s)
globalThis.__ = t

const existingCustomer = {
	name: "CUST-2026-68541",
	customer_name: "ZZ Test POSSync1",
	mobile_no: "+964-7754539344",
	email_id: "pos.9647754539344@pos.miraaya",
}

function createResourceOnSuccess(url) {
	const entry = resourceConfigs.find((item) => item.opts.url === url)
	if (!entry) throw new Error(`createResource not called for ${url}`)
	return entry.opts.onSuccess
}

function factory() {
	return mount(CreateCustomerDialog, {
		props: { modelValue: false, posProfile: "POS-A" },
		global: { mocks: { __: t } },
	})
}

const find = (wrapper, id) => wrapper.find(`[data-testid="${id}"]`)

describe("CreateCustomerDialog existing-customer response", () => {
	beforeEach(() => {
		resourceConfigs.length = 0
		showSuccess.mockReset()
		showError.mockReset()
		canCreateCustomer.mockReset()
		canCreateCustomer.mockResolvedValue(true)
	})

	afterEach(() => {
		document.body.innerHTML = ""
	})

	it("shows Magento's exact email message and lets the cashier select the existing customer", async () => {
		const wrapper = factory()
		const onSuccess = createResourceOnSuccess("pos_next.api.customers.create_customer")
		const message = "A customer with this email already exists."

		await onSuccess({
			already_exists: true,
			message,
			existing_customer: existingCustomer,
		})
		await flushPromises()

		const warning = find(wrapper, "existing-customer-warning")
		expect(warning.exists()).toBe(true)
		expect(warning.text()).toContain(message)
		expect(warning.text()).toContain("ZZ Test POSSync1")
		expect(warning.text()).toContain("CUST-2026-68541")
		expect(wrapper.text()).toContain("Select this customer")
		expect(wrapper.text()).toContain("Back")
		expect(showSuccess).not.toHaveBeenCalled()
		expect(showError).not.toHaveBeenCalled()
		expect(wrapper.emitted("customer-created")).toBeFalsy()

		const buttons = wrapper.findAll("button")
		const select = buttons.find((btn) => btn.text() === "Select this customer")
		expect(select).toBeTruthy()
		await select.trigger("click")
		expect(wrapper.emitted("customer-created")[0][0]).toEqual(existingCustomer)
		expect(wrapper.emitted("update:modelValue")[0]).toEqual([false])
		wrapper.unmount()
	})

	it("shows Magento's exact phone message and does not create a new customer", async () => {
		const wrapper = factory()
		const onSuccess = createResourceOnSuccess("pos_next.api.customers.create_customer")
		const message = "A customer with this phone already exists."

		await onSuccess({
			already_exists: true,
			message,
			existing_customer: existingCustomer,
		})
		await flushPromises()

		const warning = find(wrapper, "existing-customer-warning")
		expect(warning.exists()).toBe(true)
		expect(warning.text()).toContain(message)
		expect(warning.text()).toContain("+964-7754539344")
		expect(showSuccess).not.toHaveBeenCalled()
		expect(wrapper.emitted("customer-created")).toBeFalsy()

		const buttons = wrapper.findAll("button")
		const back = buttons.find((btn) => btn.text() === "Back")
		expect(back).toBeTruthy()
		await back.trigger("click")
		await flushPromises()
		expect(find(wrapper, "existing-customer-warning").exists()).toBe(false)
		expect(wrapper.emitted("customer-created")).toBeFalsy()
		wrapper.unmount()
	})
})
