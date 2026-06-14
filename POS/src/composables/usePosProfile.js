import { createResource } from "frappe-ui"
import { ref } from "vue"

export function usePosProfile() {
	const selectedProfile = ref(null)

	// Get all POS Profiles accessible by user
	const getPosProfiles = createResource({
		url: "pos_next.api.pos_profile.get_pos_profiles",
		auto: false,
	})

	// Get detailed POS Profile data
	const getPosProfileData = createResource({
		url: "pos_next.api.pos_profile.get_pos_profile_data",
		makeParams({ pos_profile }) {
			return { pos_profile }
		},
		auto: false,
		onSuccess(data) {
			selectedProfile.value = data.pos_profile
		},
	})

	function selectProfile(profile) {
		selectedProfile.value = profile
	}

	function clearProfile() {
		selectedProfile.value = null
	}

	return {
		selectedProfile,
		getPosProfiles,
		getPosProfileData,
		selectProfile,
		clearProfile,
	}
}
