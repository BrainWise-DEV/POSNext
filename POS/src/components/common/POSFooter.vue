<template>
	<div ref="footerRoot" :class="footerClass" :style="footerStyle" :data-bw-sig="brandSignature"
		@contextmenu.prevent @selectstart.prevent>
		<div class="footer-content" dir="ltr">
			<span class="footer-text">{{ footerText }}</span>
			<a :href="footerLink" target="_blank" rel="noopener noreferrer" class="footer-link"
				@click="handleLinkClick">
				{{ linkText }}
			</a>
		</div>
	</div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { call } from '@/utils/apiWrapper'

// Component state
const footerText = ref('Powered by')
const linkText = ref('BrainWise')
const footerLink = ref('https://nexus.brainwise.me')
const footerRoot = ref(null)
const config = ref({})
const serverValidationEnabled = ref(true)

// Dynamic class and style to prevent easy CSS targeting
const componentId = Math.random().toString(36).substring(7)
const footerClass = ref(`pos-footer-component pos-footer-component-${componentId}`)
const brandSignature = computed(() => `BrainWise-${componentId}`)

const footerStyle = computed(() => ({
	padding: config.value._s?.p || '12px 20px',
	backgroundColor: config.value._s?.bg || '#f8f9fa',
	borderTop: config.value._s?.bt || '1px solid #e0e0e0',
	textAlign: config.value._s?.ta || 'center',
	fontSize: config.value._s?.fs || '13px',
	color: config.value._s?.c || '#6b7280',
	zIndex: config.value._s?.z || 100,
	userSelect: 'none',
	WebkitUserSelect: 'none',
	MozUserSelect: 'none',
	msUserSelect: 'none',
	position: 'fixed',
	bottom: '0',
	left: '0',
	right: '0',
	width: '100%'
}))

// Protection mechanisms
let integrityTimer = null
let visibilityObserver = null
let styleElement = null
let originalParent = null
let originalNextSibling = null
let validationTimer = null

// Load branding configuration from backend
const loadBrandingConfig = async () => {
	try {
		const response = await call('pos_next.api.branding.get_branding_config')

		if (response) {
			config.value = response

			// Decode base64 encoded values
			footerText.value = atob(response._t || '')
			linkText.value = atob(response._l || '')
			footerLink.value = atob(response._u || '')
			serverValidationEnabled.value = response._v || false

			// Update check interval if provided
			if (response._i && integrityTimer) {
				clearInterval(integrityTimer)
				integrityTimer = setInterval(checkIntegrity, response._i)
			}

			// Start server validation if enabled
			if (serverValidationEnabled.value) {
				startServerValidation()
			}
		}
	} catch (error) {
		console.error('[BrainWise] Failed to load branding config:', error)
		// Use fallback values
		footerText.value = 'Powered by'
		linkText.value = 'BrainWise'
		footerLink.value = 'https://nexus.brainwise.me'
	}
}

// Server-side validation
const validateWithServer = async () => {
	if (!serverValidationEnabled.value) return

	try {
		await call('pos_next.api.branding.validate_branding', {
			client_signature: config.value._sig,
			brand_name: linkText.value,
			brand_url: footerLink.value
		})
	} catch (error) {
		console.error('[BrainWise] Server validation failed:', error)
	}
}

const startServerValidation = () => {
	// Validate with server every 5 minutes
	validationTimer = setInterval(validateWithServer, 300000)
	// Initial validation
	validateWithServer()
}

// Log client-side events to server
const logClientEvent = async (eventType, details = {}) => {
	try {
		await call('pos_next.api.branding.log_client_event', {
			event_type: eventType,
			details: JSON.stringify({
				...details,
				timestamp: Date.now(),
				component_id: componentId
			})
		})
	} catch (error) {
		console.error('[BrainWise] Failed to log event:', error)
	}
}

const ensureBranding = () => {
	if (!footerRoot.value) return

	const expectedBrand = atob(config.value._l || btoa('BrainWise'))
	const expectedUrl = atob(config.value._u || btoa('https://nexus.brainwise.me'))
	const expectedText = atob(config.value._t || btoa('Powered by'))

	// Check if values have been tampered
	if (linkText.value !== expectedBrand) {
		linkText.value = expectedBrand
		logClientEvent('modification', { field: 'brand_name', attempted_value: linkText.value })
	}
	if (footerLink.value !== expectedUrl) {
		footerLink.value = expectedUrl
		logClientEvent('modification', { field: 'brand_url', attempted_value: footerLink.value })
	}
	if (footerText.value !== expectedText) {
		footerText.value = expectedText
		logClientEvent('modification', { field: 'brand_text', attempted_value: footerText.value })
	}

	const linkEl = footerRoot.value.querySelector('.footer-link')
	if (linkEl) {
		if (linkEl.textContent.trim() !== expectedBrand) {
			linkEl.textContent = expectedBrand
		}
		if (linkEl.getAttribute('href') !== expectedUrl) {
			linkEl.setAttribute('href', expectedUrl)
		}
		linkEl.setAttribute('rel', 'noopener noreferrer')
		linkEl.setAttribute('target', '_blank')
	}

	const textEl = footerRoot.value.querySelector('.footer-text')
	if (textEl && textEl.textContent.trim() !== expectedText) {
		textEl.textContent = expectedText
	}
}

const ensureStylePresence = () => {
	if (!styleElement || !document.head.contains(styleElement)) {
		styleElement = document.createElement('style')
		styleElement.textContent = `
			.pos-footer-component {
				pointer-events: auto !important;
				min-height: 45px;
				position: fixed !important;
				bottom: 0 !important;
				left: 0 !important;
				right: 0 !important;
			}
			.pos-footer-component .footer-content {
				display: flex;
				align-items: center;
				justify-content: center;
				gap: 6px;
			}
			.pos-footer-component .footer-text {
				color: #6b7280;
			}
			.pos-footer-component .footer-link {
				color: #3b82f6;
				text-decoration: none;
				font-weight: 600;
				transition: color 0.2s;
			}
			.pos-footer-component .footer-link:hover {
				color: #2563eb;
				text-decoration: underline;
			}
		`
		document.head.appendChild(styleElement)
	}
}

const restoreFooter = () => {
	if (!footerRoot.value) return

	const rootEl = footerRoot.value
	const isInDom = document.body.contains(rootEl)

	if (!isInDom) {
		logClientEvent('removal', { restored: true })

		const parentTarget = (originalParent && document.contains(originalParent)) ? originalParent : document.body

		if (originalNextSibling && originalNextSibling.parentNode === parentTarget) {
			parentTarget.insertBefore(rootEl, originalNextSibling)
		} else {
			parentTarget.appendChild(rootEl)
		}
	}

	ensureBranding()
}

// Track link clicks
const handleLinkClick = () => {
	const timestamp = Date.now()
	sessionStorage.setItem('_bw_lc', timestamp.toString())
	logClientEvent('link_click', { url: footerLink.value })
}

// Integrity check function
const checkIntegrity = () => {
	const elements = document.querySelectorAll('.pos-footer-component')

	if (elements.length === 0) {
		console.warn('[POS System] Footer component integrity check failed')
		sessionStorage.setItem('_bw_ic', Date.now().toString())
		logClientEvent('integrity_fail', { reason: 'element_not_found' })
		restoreFooter()
	} else {
		// Check visibility
		elements.forEach(el => {
			const style = window.getComputedStyle(el)
			if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
				console.warn('[POS System] Footer visibility modified')
				sessionStorage.setItem('_bw_vc', Date.now().toString())
				logClientEvent('visibility_change', {
					display: style.display,
					visibility: style.visibility,
					opacity: style.opacity
				})
				el.style.display = 'flex'
				el.style.visibility = 'visible'
				el.style.opacity = '1'
			}
			// Ensure position stays fixed
			if (style.position !== 'fixed') {
				el.style.position = 'fixed'
				el.style.bottom = '0'
				el.style.left = '0'
				el.style.right = '0'
			}
		})
	}

	ensureStylePresence()
	ensureBranding()
}

// Mutation observer to detect DOM changes
const observeFooter = () => {
	if (typeof MutationObserver !== 'undefined') {
		const targetNode = document.body
		const observerConfig = {
			childList: true,
			subtree: true,
			attributes: true,
			attributeFilter: ['style', 'class']
		}

		visibilityObserver = new MutationObserver((mutations) => {
			mutations.forEach((mutation) => {
				if (mutation.type === 'childList' || mutation.type === 'attributes') {
					const footerExists = document.querySelector('.pos-footer-component')
					if (!footerExists && mutation.removedNodes.length > 0) {
						sessionStorage.setItem('_bw_rm', Date.now().toString())
						logClientEvent('removal', { mutation_type: mutation.type })
						restoreFooter()
					}
					if (mutation.target && footerRoot.value && mutation.target === footerRoot.value) {
						ensureBranding()
					}
				}
			})
		})

		visibilityObserver.observe(targetNode, observerConfig)
	}
}

// Lifecycle hooks
onMounted(async () => {
	// Load configuration from backend
	await loadBrandingConfig()

	// Start integrity checks
	const checkInterval = config.value._i || 10000
	integrityTimer = setInterval(checkIntegrity, checkInterval)

	// Start DOM observation
	observeFooter()

	// Initial integrity check
	setTimeout(checkIntegrity, 1000)

	// Add protective CSS dynamically
	ensureStylePresence()

	if (footerRoot.value) {
		originalParent = footerRoot.value.parentNode
		originalNextSibling = footerRoot.value.nextSibling
		ensureBranding()
	}

	if (typeof window !== 'undefined') {
		window.addEventListener('focus', ensureBranding, { passive: true })
	}
})

onBeforeUnmount(() => {
	// Cleanup
	if (integrityTimer) {
		clearInterval(integrityTimer)
	}
	if (validationTimer) {
		clearInterval(validationTimer)
	}
	if (visibilityObserver) {
		visibilityObserver.disconnect()
	}
	if (styleElement && document.head.contains(styleElement)) {
		document.head.removeChild(styleElement)
	}
	if (typeof window !== 'undefined') {
		window.removeEventListener('focus', ensureBranding)
	}
})
</script>

<style scoped>
/* Minimal scoped styles - main styles are injected dynamically */
.pos-footer-component {
	flex-shrink: 0;
}
</style>
