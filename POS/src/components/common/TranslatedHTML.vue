<template>
    <component :is="tag" :="$attrs" ref="containerRef">
    </component>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import DOMPurify from 'dompurify'

const props = defineProps({
    tag: {
        type: String,
        required: false,
        default: 'span'
    },
    inner: {
        type: String,
        required: true
    }
})

const containerRef = ref(null)

onMounted(() => {
    const sanitized = DOMPurify.sanitize(props.inner)
    containerRef.value.innerHTML = sanitized
})
</script>