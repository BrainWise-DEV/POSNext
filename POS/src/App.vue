<template>
	<div>
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
