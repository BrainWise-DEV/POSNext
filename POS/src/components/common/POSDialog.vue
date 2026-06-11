<template>
	<Dialog v-bind="$attrs">
		<template v-if="$slots.body" #body>
			<div class="pos-dialog-interactive-area" @pointerdown.stop @dragstart.prevent>
				<slot name="body" />
			</div>
		</template>

		<template v-if="$slots['body-title']" #body-title>
			<slot name="body-title" />
		</template>

		<template v-if="$slots['body-content']" #body-content>
			<div class="pos-dialog-interactive-area" @pointerdown.stop @dragstart.prevent>
				<slot name="body-content" />
			</div>
		</template>

		<template v-if="$slots.actions" #actions="slotProps">
			<div class="pos-dialog-interactive-area" @pointerdown.stop @dragstart.prevent>
				<slot name="actions" v-bind="slotProps" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { Dialog } from "frappe-ui"

defineOptions({
	inheritAttrs: false,
})
</script>

<style scoped>
.pos-dialog-interactive-area {
	-webkit-user-select: none;
	user-select: none;
}

.pos-dialog-interactive-area :deep(input),
.pos-dialog-interactive-area :deep(textarea),
.pos-dialog-interactive-area :deep([contenteditable="true"]) {
	-webkit-user-select: text;
	user-select: text;
}
</style>
