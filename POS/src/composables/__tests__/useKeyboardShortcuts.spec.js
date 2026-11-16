/** @vitest-environment jsdom */
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { defineComponent, ref } from "vue";
import { useGlobalShortcuts, usePickerEnter } from "@/composables/useKeyboardShortcuts";

const press = (target, key) =>
	target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));

function mountWith(setupFn) {
	return mount(defineComponent({ setup: setupFn, template: "<div />" }), { attachTo: document.body });
}

describe("useGlobalShortcuts", () => {
	it("fires F-keys while an input has focus", () => {
		const onPayment = vi.fn();
		const wrapper = mountWith(() => useGlobalShortcuts(() => false, { F9: onPayment }));
		const input = document.createElement("input");
		document.body.appendChild(input);
		input.focus();
		press(input, "F9");
		expect(onPayment).toHaveBeenCalledTimes(1);
		wrapper.unmount();
		press(input, "F9");
		expect(onPayment).toHaveBeenCalledTimes(1);
	});

	it("keeps non F-keys guarded in inputs and honours the block guard", () => {
		const onKey = vi.fn();
		const blocked = ref(false);
		const wrapper = mountWith(() => useGlobalShortcuts(() => blocked.value, { "/": onKey, F4: onKey }));
		const input = document.createElement("input");
		document.body.appendChild(input);
		input.focus();
		press(input, "/");
		expect(onKey).not.toHaveBeenCalled();
		blocked.value = true;
		press(input, "F4");
		expect(onKey).not.toHaveBeenCalled();
		wrapper.unmount();
	});
});

describe("usePickerEnter", () => {
	it("runs the handler on Enter only while open and not from an input", async () => {
		const onEnter = vi.fn();
		const open = ref(false);
		const wrapper = mountWith(() => usePickerEnter(open, onEnter));
		const button = document.createElement("button");
		const input = document.createElement("input");
		document.body.append(button, input);
		press(button, "Enter");
		expect(onEnter).not.toHaveBeenCalled();
		open.value = true;
		await Promise.resolve();
		const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
		button.dispatchEvent(event);
		expect(onEnter).toHaveBeenCalledTimes(1);
		expect(event.defaultPrevented).toBe(true);
		press(input, "Enter");
		expect(onEnter).toHaveBeenCalledTimes(1);
		wrapper.unmount();
	});
});
