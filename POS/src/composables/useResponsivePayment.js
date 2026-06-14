/**
 * Responsive Payment Dialog Composable
 * Handles viewport tracking and dynamic sizing for payment dialog
 */

import { ref, computed, onMounted, onUnmounted } from "vue"

export function useResponsivePayment() {
	// Viewport dimension tracking
	const viewportWidth = ref(typeof window !== "undefined" ? window.innerWidth : 1200)
	const viewportHeight = ref(typeof window !== "undefined" ? window.innerHeight : 800)

	function updateViewportDimensions() {
		viewportWidth.value = window.innerWidth
		viewportHeight.value = window.innerHeight
	}

	onMounted(() => {
		updateViewportDimensions()
		window.addEventListener("resize", updateViewportDimensions)
	})

	onUnmounted(() => {
		window.removeEventListener("resize", updateViewportDimensions)
	})

	// Dynamic dialog size based on viewport
	const dynamicDialogSize = computed(() => {
		const width = viewportWidth.value
		if (width < 640) return "full" // Mobile: full screen
		if (width < 768) return "full" // Small tablet: full screen for better usability
		if (width < 1024) return "4xl" // Tablet
		if (width < 1280) return "5xl" // Small desktop
		return "6xl" // Large desktop
	})

	// Check if we're on a mobile device (for mobile-specific behavior)
	const isMobileView = computed(() => viewportWidth.value < 1024)

	// Dynamic content max height based on viewport
	const dialogContentMaxHeight = computed(() => {
		const height = viewportHeight.value
		const width = viewportWidth.value

		// On mobile, don't set max-height - let content determine size
		if (width < 1024) {
			return "none"
		}
		// Desktop: use fixed pixel calculation
		const availableHeight = height - 100
		return `${Math.min(Math.max(500, availableHeight), height - 80)}px`
	})

	// Dynamic column heights based on viewport
	const dynamicLeftColumnHeight = computed(() => {
		const height = viewportHeight.value
		if (viewportWidth.value < 1024) {
			// Mobile/tablet: auto height, will stack
			return "auto"
		}
		// Desktop: calculate based on available space
		const availableHeight = height - 160 // Header + padding + action buttons
		return `${Math.max(400, Math.min(availableHeight, height - 120))}px`
	})

	// Check if we're in compact mode (small screens)
	const isCompactMode = computed(() => viewportHeight.value < 700 || viewportWidth.value < 1024)

	// Check if we're on a very small mobile screen
	const isSmallMobile = computed(() => viewportWidth.value < 360 || viewportHeight.value < 600)

	// Dynamic gap and padding based on screen size
	const dynamicGap = computed(() => {
		if (viewportWidth.value < 360) return "gap-1" // Very small phones
		if (viewportWidth.value < 640) return "gap-1.5"
		if (viewportWidth.value < 1024) return "gap-2"
		return "gap-3"
	})

	// Dynamic text sizes
	const dynamicTextSize = computed(() => {
		const width = viewportWidth.value
		const height = viewportHeight.value

		// Very small phones
		if (width < 360 || height < 550) {
			return {
				header: "text-[10px]",
				body: "text-[10px]",
				amount: "text-base",
				grandTotal: "text-base",
			}
		}
		// Small phones
		if (width < 640) {
			return {
				header: "text-xs",
				body: "text-xs",
				amount: "text-lg",
				grandTotal: "text-lg",
			}
		}
		// Tablet and small height screens
		if (height < 700) {
			return {
				header: "text-sm",
				body: "text-sm",
				amount: "text-lg",
				grandTotal: "text-xl",
			}
		}
		// Default desktop
		return {
			header: "text-sm",
			body: "text-sm",
			amount: "text-xl",
			grandTotal: "text-2xl",
		}
	})

	// Dynamic button heights
	const dynamicButtonHeight = computed(() => {
		const width = viewportWidth.value
		const height = viewportHeight.value

		// Very small phones - smaller buttons
		if (width < 360 || height < 550) return "h-9"
		// Small phones
		if (width < 640) return "h-10"
		// Short screens
		if (height < 700) return "h-10"
		return "h-12"
	})

	// Mobile action button sizing
	const mobileButtonSize = computed(() => {
		const width = viewportWidth.value
		const height = viewportHeight.value

		if (width < 360 || height < 550) {
			return {
				height: "h-9",
				text: "text-xs",
				icon: "w-3.5 h-3.5",
				gap: "gap-1",
			}
		}
		if (width < 640) {
			return {
				height: "h-10",
				text: "text-sm",
				icon: "w-4 h-4",
				gap: "gap-1.5",
			}
		}
		return {
			height: "h-11",
			text: "text-sm",
			icon: "w-4 h-4",
			gap: "gap-2",
		}
	})

	// Dynamic numpad key size
	const dynamicNumpadSize = computed(() => {
		if (viewportHeight.value < 600) return { key: "h-10", addBtn: "h-[6.5rem]" }
		if (viewportHeight.value < 700) return { key: "h-10", addBtn: "h-[7rem]" }
		return { key: "h-12", addBtn: "h-[8.5rem]" }
	})

	return {
		// State
		viewportWidth,
		viewportHeight,

		// Computed
		dynamicDialogSize,
		isMobileView,
		dialogContentMaxHeight,
		dynamicLeftColumnHeight,
		isCompactMode,
		isSmallMobile,
		dynamicGap,
		dynamicTextSize,
		dynamicButtonHeight,
		mobileButtonSize,
		dynamicNumpadSize,
	}
}
