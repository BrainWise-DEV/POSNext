import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const resources = {};
const call = vi.fn();

vi.mock("frappe-ui", () => ({
	createResource: ({ url }) => ({
		submit: (...args) => resources[url](...args),
		fetch: vi.fn(),
		reload: vi.fn(),
		data: null,
		error: null,
	}),
	call: vi.fn(),
}));
vi.mock("@/utils/apiWrapper", () => ({ call: (...args) => call(...args) }));
vi.mock("@/utils/offline", () => ({
	isOffline: () => false,
	getCachedItem: vi.fn(),
}));
vi.mock("@/stores/serialNumber", () => ({
	useSerialNumberStore: () => ({ returnSerials: vi.fn() }),
}));

const { useInvoice } = await import("../useInvoice");

const DRAFT = { name: "ACC-SINV-DRAFT", docstatus: 0 };
const SUBMITTED = { name: "ACC-SINV-1", status: 1, grand_total: 20, paid_amount: 20 };

function newInvoiceWithCart() {
	const invoice = useInvoice();
	invoice.posProfile.value = "P1";
	invoice.customer.value = { name: "C1", customer_name: "C1" };
	invoice.invoiceItems.value = [
		{
			item_code: "A",
			item_name: "A",
			quantity: 2,
			rate: 10,
			price_list_rate: 10,
			uom: "Nos",
			warehouse: "W1",
		},
	];
	invoice.payments.value = [{ mode_of_payment: "Cash", amount: 20, type: "Cash" }];
	return invoice;
}

const submitCalls = () => resources["pos_next.api.invoices.submit_invoice"].mock.calls;
const requestIdOf = (callArgs) =>
	JSON.parse(callArgs[0].data ? JSON.stringify(callArgs[0].data) : "{}").client_request_id;

describe("useInvoice submit gate and timeout recovery", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		vi.useFakeTimers();
		call.mockReset();
		resources["pos_next.api.invoices.update_invoice"] = vi.fn().mockResolvedValue(DRAFT);
		resources["pos_next.api.invoices.submit_invoice"] = vi.fn().mockResolvedValue(SUBMITTED);
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it("a double-click is dropped, not re-run against the cleared cart", async () => {
		let finish;
		resources["pos_next.api.invoices.submit_invoice"] = vi.fn(
			() =>
				new Promise((resolve) => {
					finish = () => resolve(SUBMITTED);
				})
		);
		const invoice = newInvoiceWithCart();

		const first = invoice.submitInvoice();
		await vi.advanceTimersByTimeAsync(0);
		const second = await invoice.submitInvoice();
		expect(second).toBeNull();

		finish();
		expect(await first).toEqual(SUBMITTED);
		await vi.advanceTimersByTimeAsync(0);

		expect(resources["pos_next.api.invoices.update_invoice"]).toHaveBeenCalledTimes(1);
		expect(submitCalls()).toHaveLength(1);
		expect(invoice.invoiceItems.value).toHaveLength(0);
	});

	it("after a timeout, finishes the checkout when the server already has the sale", async () => {
		resources["pos_next.api.invoices.submit_invoice"] = vi.fn(() => new Promise(() => {}));
		call.mockResolvedValue({ synced: true, sales_invoice: "ACC-SINV-1", invoice: SUBMITTED });
		const invoice = newInvoiceWithCart();

		const pending = invoice.submitInvoice();
		await vi.advanceTimersByTimeAsync(60000);
		const result = await pending;

		expect(result).toEqual(SUBMITTED);
		expect(call).toHaveBeenCalledWith("pos_next.api.invoices.check_offline_invoice_synced", {
			offline_id: expect.stringMatching(/^pos_online_/),
		});
		expect(invoice.invoiceItems.value).toHaveLength(0); // sale completed: cart cleared
		expect(invoice.isSubmitting.value).toBe(false);
	});

	it("when the sale is not found, keeps the cart and a retry reuses the same key", async () => {
		resources["pos_next.api.invoices.submit_invoice"] = vi.fn(() => new Promise(() => {}));
		call.mockResolvedValue({ synced: false });
		const invoice = newInvoiceWithCart();

		const pending = invoice.submitInvoice();
		pending.catch(() => {});
		await vi.advanceTimersByTimeAsync(60000 + 4 * 2500);
		await expect(pending).rejects.toMatchObject({ timeoutUnresolved: true });
		await expect(pending).rejects.toThrow(/Retrying will not create a duplicate/);

		expect(invoice.invoiceItems.value).toHaveLength(1); // nothing lost
		expect(invoice.isSubmitting.value).toBe(false); // cashier can retry

		const firstKey = requestIdOf(submitCalls()[0]);

		resources["pos_next.api.invoices.submit_invoice"].mockResolvedValueOnce(SUBMITTED);
		await invoice.submitInvoice();
		const retryKey = requestIdOf(submitCalls()[1]);

		expect(firstKey).toMatch(/^pos_online_/);
		expect(retryKey).toBe(firstKey);
	});

	it("an abandoned first request finishing later does not wipe a new cart", async () => {
		let finishFirst;
		resources["pos_next.api.invoices.submit_invoice"] = vi
			.fn()
			.mockImplementationOnce(
				() =>
					new Promise((resolve) => {
						finishFirst = () => resolve(SUBMITTED);
					})
			)
			.mockImplementation(() => new Promise(() => {}));
		call.mockResolvedValue({ synced: false });
		const invoice = newInvoiceWithCart();

		const pending = invoice.submitInvoice();
		pending.catch(() => {});
		await vi.advanceTimersByTimeAsync(60000 + 4 * 2500);
		await expect(pending).rejects.toMatchObject({ timeoutUnresolved: true });

		finishFirst(); // the timed-out request completes afterwards
		await vi.advanceTimersByTimeAsync(0);

		expect(invoice.invoiceItems.value).toHaveLength(1); // cart not wiped by the stale request
	});
});

describe("useInvoice deadlock retry", () => {
	const deadlock = () =>
		Object.assign(new Error("Internal Server Error"), { exc_type: "QueryDeadlockError" });

	beforeEach(() => {
		setActivePinia(createPinia());
		vi.useFakeTimers();
		call.mockReset();
		resources["pos_next.api.invoices.update_invoice"] = vi.fn().mockResolvedValue(DRAFT);
		resources["pos_next.api.invoices.submit_invoice"] = vi.fn().mockResolvedValue(SUBMITTED);
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it("a deadlock on the submit call is retried invisibly, with the same key", async () => {
		resources["pos_next.api.invoices.submit_invoice"] = vi
			.fn()
			.mockRejectedValueOnce(deadlock())
			.mockResolvedValue(SUBMITTED);
		const invoice = newInvoiceWithCart();

		const pending = invoice.submitInvoice();
		await vi.advanceTimersByTimeAsync(2000);

		expect(await pending).toEqual(SUBMITTED);
		expect(submitCalls()).toHaveLength(2);
		expect(requestIdOf(submitCalls()[1])).toBe(requestIdOf(submitCalls()[0]));
		expect(resources["pos_next.api.invoices.update_invoice"]).toHaveBeenCalledTimes(1);
		expect(invoice.invoiceItems.value).toHaveLength(0);
	});

	it("a deadlock while creating the draft is retried too", async () => {
		resources["pos_next.api.invoices.update_invoice"] = vi
			.fn()
			.mockRejectedValueOnce(deadlock())
			.mockResolvedValue(DRAFT);
		const invoice = newInvoiceWithCart();

		const pending = invoice.submitInvoice();
		await vi.advanceTimersByTimeAsync(2000);

		expect(await pending).toEqual(SUBMITTED);
		expect(resources["pos_next.api.invoices.update_invoice"]).toHaveBeenCalledTimes(2);
	});

	it("keeps failing deadlocks visible after 3 attempts and keeps the cart", async () => {
		resources["pos_next.api.invoices.submit_invoice"] = vi.fn().mockRejectedValue(deadlock());
		const invoice = newInvoiceWithCart();

		const pending = invoice.submitInvoice();
		pending.catch(() => {});
		await vi.advanceTimersByTimeAsync(5000);

		await expect(pending).rejects.toMatchObject({ exc_type: "QueryDeadlockError" });
		expect(submitCalls()).toHaveLength(3);
		expect(invoice.invoiceItems.value).toHaveLength(1);
		expect(invoice.isSubmitting.value).toBe(false);
	});

	it("other errors are not retried", async () => {
		const stock = Object.assign(new Error("1 units needed in"), {
			exc_type: "NegativeStockError",
		});
		resources["pos_next.api.invoices.submit_invoice"] = vi.fn().mockRejectedValue(stock);
		const invoice = newInvoiceWithCart();

		await expect(invoice.submitInvoice()).rejects.toBe(stock);
		expect(submitCalls()).toHaveLength(1);
	});
});
