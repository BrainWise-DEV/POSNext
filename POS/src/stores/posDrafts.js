import {
	deleteDraft,
	getDraftsCount,
	saveDraft,
	getAllDrafts,
	updateDraft,
} from "@/utils/draftManager";
import { useToast } from "@/composables/useToast";
import { useSerialNumberStore } from "@/stores/serialNumber";
import { defineStore } from "pinia";
import { ref } from "vue";

export const usePOSDraftsStore = defineStore("posDrafts", () => {
	// Use custom toast
	const { showSuccess, showError, showWarning } = useToast();
	const serialStore = useSerialNumberStore();

	// State
	const draftsCount = ref(0);
	const drafts = ref([]);

	// Actions
	async function updateDraftsCount() {
		try {
			draftsCount.value = await getDraftsCount();
		} catch (error) {
			console.error("Error getting drafts count:", error);
		}
	}

	async function loadDrafts() {
		try {
			drafts.value = await getAllDrafts();
			draftsCount.value = drafts.value.length;
		} catch (error) {
			console.error("Error loading drafts:", error);
		}
	}

	async function saveDraftInvoice(
		invoiceItems,
		customer,
		posProfile,
		appliedOffers = [],
		draftId = null
	) {
		if (invoiceItems.length === 0) {
			showWarning(__("Cannot save an empty cart as draft"));
			return null;
		}

		try {
			const draftData = {
				pos_profile: posProfile,
				customer: customer,
				items: invoiceItems,
				applied_offers: appliedOffers, // Save applied offers
			};

			let savedDraft;
			if (draftId) {
				savedDraft = await updateDraft(draftId, draftData);
			} else {
				savedDraft = await saveDraft(draftData);
			}

			await loadDrafts(); // Refresh drafts list and count

			showSuccess(__("Invoice saved as draft successfully"));

			return savedDraft;
		} catch (error) {
			console.error("Error saving draft:", error);
			showError(__("Failed to save draft"));
			return null;
		}
	}

	async function loadDraft(draft) {
		try {
			showSuccess(__("Draft invoice loaded successfully"));

			return {
				items: draft.items || [],
				customer: draft.customer,
				applied_offers: draft.applied_offers || [], // Restore applied offers
			};
		} catch (error) {
			console.error("Error loading draft:", error);
			showError(__("Failed to load draft"));
			throw error;
		}
	}

	// Return a parked draft's serials to the offline cache
	function returnDraftSerials(draft) {
		for (const item of draft?.items || []) {
			if (item.has_serial_no && item.serial_no) {
				serialStore.returnSerials(item.item_code, item.serial_no);
			}
		}
	}

	/**
	 * @param {{ returnSerials?: boolean }} [options]
	 *   true when the user discards the draft; false (default) after the draft was sold
	 */
	async function deleteDraftById(draftId, { returnSerials = false } = {}) {
		try {
			const draft = drafts.value.find((d) => d.draft_id === draftId);
			await deleteDraft(draftId);
			if (returnSerials) returnDraftSerials(draft);
			await loadDrafts(); // Refresh drafts list and count
			showSuccess(__("Draft deleted successfully"));
		} catch (error) {
			console.error("Error deleting draft:", error);
			showError(__("Failed to delete draft"));
		}
	}

	return {
		// State
		draftsCount,
		drafts,

		// Actions
		updateDraftsCount,
		loadDrafts,
		saveDraftInvoice,
		loadDraft,
		deleteDraft: deleteDraftById,
		returnDraftSerials,
	};
});
