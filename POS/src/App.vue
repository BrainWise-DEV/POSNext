<template>
	<div class="flex flex-1 flex-col min-h-0">
		<router-view :key="translationVersion" />
		<Toast />
		<AuthorizationDialog />
	</div>
</template>

<script setup>
import AuthorizationDialog from "@/components/common/AuthorizationDialog.vue";
import Toast from "@/components/common/Toast.vue";
import { translationVersion } from "@/utils/translation";
</script>
