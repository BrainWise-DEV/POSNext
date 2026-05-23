<template>
	<Dialog v-bind="$attrs">
		<template v-if="$slots.body" #body>
			<div @pointerdown.stop>
				<slot name="body" />
			</div>
		</template>

		<template v-if="$slots['body-title']" #body-title>
			<slot name="body-title" />
		</template>

		<template v-if="$slots['body-content']" #body-content>
			<div @pointerdown.stop>
				<slot name="body-content" />
			</div>
		</template>

		<template v-if="$slots.actions" #actions="slotProps">
			<div @pointerdown.stop>
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
