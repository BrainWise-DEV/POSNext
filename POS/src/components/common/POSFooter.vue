<template>
	<div class="pos-footer-component">
		<div class="footer-content" dir="ltr">
			<span class="footer-text">Powered by</span>
			<a :href="footerLink" target="_blank" rel="noopener noreferrer" class="footer-link">
				{{ linkText }}
			</a>
		</div>
	</div>
</template>

<script setup>
const linkText = "Blaze Technology Solutions"
const footerLink = "https://blazeqatar.com/"
</script>

<style scoped>
.pos-footer-component {
	position: fixed;
	bottom: 0;
	left: 0;
	right: 0;
	width: 100%;
	padding: 12px 20px;
	background-color: #f8f9fa;
	border-top: 1px solid #e0e0e0;
	text-align: center;
	font-size: 13px;
	color: #6b7280;
	z-index: 100;
}
.footer-content {
	display: flex;
	align-items: center;
	justify-content: center;
	gap: 6px;
}
.footer-link {
	color: #3b82f6;
	text-decoration: none;
	font-weight: 600;
	transition: color 0.2s;
}
.footer-link:hover {
	color: #2563eb;
	text-decoration: underline;
}
</style>
