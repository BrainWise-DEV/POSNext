<template>
	<div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
		<button
			v-if="collapsible"
			@click="isCollapsed = !isCollapsed"
			class="w-full px-5 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
		>
			<div class="flex items-center gap-2.5">
				<div class="p-1.5 bg-blue-50 rounded">
					<component :is="getIcon(icon)" class="w-4 h-4 text-blue-600" />
				</div>
				<h2 class="text-base font-semibold text-gray-900">{{ title }}</h2>
			</div>
			<svg
				:class="['w-4 h-4 text-gray-400 transition-transform', isCollapsed ? '' : 'transform rotate-180']"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
			>
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
			</svg>
		</button>
		<div v-else class="px-5 py-3 border-b border-gray-100">
			<div class="flex items-center gap-2.5">
				<div class="p-1.5 bg-blue-50 rounded">
					<component :is="getIcon(icon)" class="w-4 h-4 text-blue-600" />
				</div>
				<h2 class="text-base font-semibold text-gray-900">{{ title }}</h2>
			</div>
		</div>
		<div v-show="!isCollapsed" class="p-5">
			<slot />
		</div>
	</div>
</template>

<script setup>
import { h, ref } from "vue"

const props = defineProps({
	title: {
		type: String,
		required: true,
	},
	icon: {
		type: String,
		default: "settings",
	},
	collapsible: {
		type: Boolean,
		default: false,
	},
	collapsed: {
		type: Boolean,
		default: false,
	},
})

const isCollapsed = ref(props.collapsed)

// Icon mapping
const icons = {
	settings: () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z",
			}),
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M15 12a3 3 0 11-6 0 3 3 0 016 0z",
			}),
		]),
	eye: () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M15 12a3 3 0 11-6 0 3 3 0 016 0z",
			}),
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z",
			}),
		]),
	activity: () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
			}),
		]),
	"dollar-sign": () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
			}),
		]),
	maximize: () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4",
			}),
		]),
	users: () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z",
			}),
		]),
	printer: () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z",
			}),
		]),
	truck: () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0",
			}),
		]),
	sliders: () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4",
			}),
		]),
	"more-horizontal": () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z",
			}),
		]),
	package: () =>
		h("svg", { fill: "none", stroke: "currentColor", viewBox: "0 0 24 24" }, [
			h("path", {
				"stroke-linecap": "round",
				"stroke-linejoin": "round",
				"stroke-width": "2",
				d: "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4",
			}),
		]),
}

function getIcon(iconName) {
	return icons[iconName] || icons["settings"]
}
</script>
