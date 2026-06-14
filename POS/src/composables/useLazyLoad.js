import { onBeforeUnmount, onMounted, ref } from "vue"

/**
 * Composable for lazy loading images using Intersection Observer
 * Optimizes performance by only loading images when they're about to enter the viewport
 *
 * @param {Object} options - Configuration options
 * @param {string} options.rootMargin - Margin around the viewport to trigger loading (default: "50px")
 * @param {number} options.threshold - Percentage of visibility to trigger (default: 0.01)
 * @returns {Object} { isVisible, targetRef, isLoaded, error }
 */
export function useLazyLoad(options = {}) {
	const {
		rootMargin = "50px", // Start loading 50px before element enters viewport
		threshold = 0.01, // Trigger when 1% of element is visible
	} = options

	const targetRef = ref(null)
	const isVisible = ref(false)
	const isLoaded = ref(false)
	const error = ref(null)

	let observer = null

	onMounted(() => {
		if (!targetRef.value) return

		// Check if Intersection Observer is supported
		if (!("IntersectionObserver" in window)) {
			// Fallback for browsers that don't support Intersection Observer
			isVisible.value = true
			return
		}

		observer = new IntersectionObserver(
			(entries) => {
				entries.forEach((entry) => {
					if (entry.isIntersecting && !isVisible.value) {
						isVisible.value = true
						// Once loaded, disconnect to save resources
						observer?.disconnect()
					}
				})
			},
			{
				rootMargin,
				threshold,
			},
		)

		observer.observe(targetRef.value)
	})

	onBeforeUnmount(() => {
		if (observer) {
			observer.disconnect()
			observer = null
		}
	})

	return {
		targetRef,
		isVisible,
		isLoaded,
		error,
	}
}
