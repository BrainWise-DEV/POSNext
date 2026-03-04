import { onMounted, onUnmounted } from "vue";

/**
 * useKeyboardShortcuts
 *
 * Registers POS-scoped keyboard shortcuts with strict guards:
 *   Ctrl+Shift+O  →  View Shift (only when shift is open)
 *   Ctrl+Shift+D  →  Draft Invoices
 *   Ctrl+Shift+H  →  Invoice History
 *   Ctrl+Shift+C  →  Close Shift (only when shift is open)
 *   Ctrl+Shift+N  →  Create Customer
 *   Ctrl+Alt+R    →  Return Invoice
 *
 * @param {Object} options
 * @param {import('@/stores/posUI').POSUIStore}   options.uiStore
 * @param {import('@/stores/posShift').POSShiftStore} options.shiftStore
 * @param {import('vue').Ref}                    options.editCustomer  – ref<null|Object>
 * @param {() => boolean}  [options.isLocalOverlayOpen]  – optional callback
 *        returning true when a non-uiStore overlay (Promotion, Settings,
 *        StockLookup, InvoiceManagement, InvoiceDetail) is open
 */
export function useKeyboardShortcuts({
    uiStore,
    shiftStore,
    editCustomer,
    isLocalOverlayOpen = () => false,
}) {
    function isEditableTarget(el) {
        if (!el) return false;
        const tag = el.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
        if (el.isContentEditable) return true;
        return false;
    }

    function isOnPOSPage() {
        // Match /pos or /pos/<profile-name> but NOT /reports/sales-pos etc.
        return /\/pos(\/|$)/.test(window.location.pathname);
    }

    function handler(e) {
        // ── Route guard ────────────────────────────────────────────────────────
        if (!isOnPOSPage()) return;

        // ── Input-field guard ──────────────────────────────────────────────────
        if (isEditableTarget(e.target)) return;

        // ── Dialog / overlay guard ─────────────────────────────────────────────
        if (uiStore.isAnyDialogOpen) return;
        if (isLocalOverlayOpen()) return;

        const key = e.key.toLowerCase();

        // ── Ctrl + Shift shortcuts (Alt must NOT be pressed) ───────────────────
        if (e.ctrlKey && e.shiftKey && !e.altKey && !e.metaKey) {
            switch (key) {
                case "o": // View Shift
                    if (shiftStore.hasOpenShift) {
                        e.preventDefault();
                        uiStore.showOpenShiftDialog = true;
                    }
                    break;

                case "d": // Draft Invoices
                    e.preventDefault();
                    uiStore.showDraftDialog = true;
                    break;

                case "h": // Invoice History
                    e.preventDefault();
                    uiStore.showHistoryDialog = true;
                    break;

                case "c": // Close Shift
                    if (shiftStore.hasOpenShift) {
                        e.preventDefault();
                        uiStore.showCloseShiftDialog = true;
                    }
                    break;

                case "n": // Create Customer
                    e.preventDefault();
                    editCustomer.value = null;
                    uiStore.setInitialCustomerName("");
                    uiStore.showCreateCustomerDialog = true;
                    break;
            }
        }

        // ── Ctrl + Alt + R  →  Return Invoice ─────────────────────────────────
        // (Alt must be pressed, Shift must NOT be pressed to avoid Ctrl+Shift+Alt+R)
        if (e.ctrlKey && e.altKey && !e.shiftKey && !e.metaKey && key === "r") {
            e.preventDefault();
            uiStore.showReturnDialog = true;
        }
    }

    onMounted(() => {
        document.addEventListener("keydown", handler);
    });

    onUnmounted(() => {
        document.removeEventListener("keydown", handler);
    });
}
