<template>
	<div class="flex flex-1 flex-col min-h-0">
		<router-view :key="translationVersion" />
		<Toast />
	</div>
</template>

<script setup>
import Toast from "@/components/common/Toast.vue";
import { translationVersion } from "@/utils/translation";
</script>
