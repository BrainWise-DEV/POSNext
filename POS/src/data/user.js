import router from "@/router"
import { createResource } from "frappe-ui"
import { computed, reactive } from "vue"

const getCookie = (key) => {
	const cookies = new Map(
		document.cookie.split("; ").filter(Boolean).map((c) => c.split("=").map(decodeURIComponent))
	)
	return cookies.get(key) || null
}

export const userData = reactive({
	userId: null,
	fullName: null,
	userImage: null,

	refresh() {
		this.userId = getCookie("user_id")
		this.fullName = getCookie("full_name")
		this.userImage = getCookie("user_image")
	},

	getDisplayName() {
		return this.fullName || window.frappe?.session?.user_fullname || window.frappe?.session?.user || "User"
	},

	getImageUrl() {
		return this.userImage || window.frappe?.session?.user_image || null
	},

	getInitials() {
		const parts = this.getDisplayName().split(" ").filter(Boolean)
		return parts.length >= 2 ? (parts[0][0] + parts[1][0]).toUpperCase() : this.getDisplayName().substring(0, 2).toUpperCase()
	},
})

userData.refresh()

export const useUserData = () => ({
	userName: computed(() => userData.getDisplayName()),
	userImage: computed(() => userData.getImageUrl()),
	userInitials: computed(() => userData.getInitials()),
	userId: computed(() => userData.userId),
	refresh: () => userData.refresh(),
})

export const userResource = createResource({
	url: "frappe.auth.get_logged_user",
	cache: "User",
	onError(error) {
		if (error?.exc_type === "AuthenticationError") {
			router.push({ name: "Login" })
		}
	},
})
