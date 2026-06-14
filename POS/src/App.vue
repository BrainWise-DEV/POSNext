<template>
  <div>
    <router-view :key="translationVersion" />
    <Toast />
  </div>
</template>

<script setup>
import Toast from "@/components/common/Toast.vue"
import { translationVersion } from "@/utils/translation"
</script>
