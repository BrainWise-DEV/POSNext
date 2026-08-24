<template>
	<div>
		<router-view :key="translationVersion" />
		<Toast />
		<AuthorizationDialog v-if="authGateInstalled" />
	</div>
</template>

<script setup>
import AuthorizationDialog from "@/components/common/AuthorizationDialog.vue";
import Toast from "@/components/common/Toast.vue";
import { isAuthGateInstalled } from "@/utils/promoApi";
import { translationVersion } from "@/utils/translation";

const authGateInstalled = isAuthGateInstalled();
</script>
