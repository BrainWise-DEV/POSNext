<template>
	<div class="rounded-lg border border-gray-200 bg-gray-50 p-3" data-testid="email-verification-panel">
		<!-- Verified badge (idle view only; stays correct while the email is unchanged) -->
		<div
			v-if="view === 'verified'"
			class="flex items-center gap-2 text-sm text-green-700"
			data-testid="verified-badge"
		>
			<span aria-hidden="true">✔</span>
			<span class="font-medium">{{ __("Email verified") }}</span>
			<span class="text-xs text-green-600 truncate" dir="ltr">{{ verifiedEmailShown }}</span>
		</div>

		<!-- idle / expired -->
		<div v-else-if="view === 'idle' || view === 'expired'" class="flex flex-col gap-2">
			<div class="flex items-center justify-between gap-2">
				<span class="text-xs text-gray-500" data-testid="not-verified-label">
					{{ __("Email not verified") }}
				</span>
				<button
					type="button"
					class="px-3 py-1.5 text-sm font-medium rounded-lg bg-blue-600 text-white disabled:bg-gray-300 disabled:cursor-not-allowed"
					data-testid="send-code"
					:disabled="!canSend"
					@click="sendCode"
				>
					{{ view === "expired" ? __("Send new code") : __("Verify email") }}
				</button>
			</div>
			<p v-if="view === 'expired'" class="text-xs text-amber-700" data-testid="expired-msg">
				{{ __("Code expired. Request a new one.") }}
			</p>
			<p v-if="offline" class="text-xs text-gray-500" data-testid="offline-msg">
				{{ __("Verification requires an internet connection.") }}
			</p>
			<p v-else-if="!emailUsable" class="text-xs text-gray-500">
				{{ __("Enter a valid email address.") }}
			</p>
			<p v-else-if="emailDirty" class="text-xs text-gray-500" data-testid="unsaved-msg">
				{{ __("Save the customer's email before verifying it.") }}
			</p>
		</div>

		<!-- sending -->
		<div
			v-else-if="view === 'sending'"
			class="flex items-center gap-2 text-sm text-gray-600"
			data-testid="sending"
		>
			<span class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
			{{ __("Sending code…") }}
		</div>

		<!-- code_sent / verifying -->
		<div v-else class="flex flex-col gap-2">
			<p class="text-sm text-gray-700" data-testid="enter-code-hint">
				{{ __("Enter the 6-digit code sent to {0}", [email]) }}
			</p>
			<div class="flex items-center gap-2">
				<input
					ref="otpInput"
					v-model="otp"
					type="text"
					inputmode="numeric"
					autocomplete="one-time-code"
					maxlength="6"
					dir="ltr"
					class="w-32 px-3 py-2 text-center tracking-widest border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
					data-testid="otp-input"
					:placeholder="__('Verification code')"
					:disabled="state === 'verifying'"
					@input="onOtpInput"
					@keydown.enter.prevent="verify"
				/>
				<button
					type="button"
					class="px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white disabled:bg-gray-300 disabled:cursor-not-allowed"
					data-testid="verify"
					:disabled="!otpComplete || state === 'verifying' || offline"
					@click="verify"
				>
					<span v-if="state === 'verifying'" data-testid="verifying">{{ __("Verifying email…") }}</span>
					<span v-else>{{ __("Verify") }}</span>
				</button>
			</div>
			<div class="flex items-center justify-between text-xs text-gray-500">
				<span data-testid="countdown">{{ __("Code expires in {0}", [countdownLabel]) }}</span>
				<button
					type="button"
					class="text-blue-600 disabled:text-gray-400 disabled:cursor-not-allowed"
					data-testid="resend"
					:disabled="cooldownRemaining > 0 || state === 'verifying' || offline"
					@click="sendCode"
				>
					<template v-if="cooldownRemaining > 0">
						{{ __("Resend available in {0}s", [cooldownRemaining]) }}
					</template>
					<template v-else>{{ __("Resend code") }}</template>
				</button>
			</div>
			<button
				type="button"
				class="self-start text-xs text-blue-600"
				data-testid="change-email"
				:disabled="state === 'verifying'"
				@click="changeEmail"
			>
				{{ __("Change email") }}
			</button>
		</div>

		<p v-if="state === 'error' && errorMessage" class="mt-2 text-xs text-red-600" data-testid="error-msg" role="alert">
			{{ errorMessage }}
		</p>
		<p v-if="infoMessage" class="mt-2 text-xs text-gray-600" data-testid="info-msg">{{ infoMessage }}</p>
	</div>
</template>

<script setup>
/**
 * EmailVerificationPanel - cashier-initiated email OTP verification.
 *
 * States: idle | sending | code_sent | verifying | verified | expired | error
 * `error` keeps the previous step visible (see returnState).
 * Nothing about the code is persisted client side; the server owns the phone
 * number (taken from Customer.mobile_no) and all rate limits.
 */
import { isOffline } from "@/utils/offline/offlineState";
import { call } from "frappe-ui";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps({
	customer: { type: String, default: "" },
	/** Email currently typed in the dialog */
	email: { type: String, default: "" },
	/** Email stored on the Customer (what the server will verify) */
	savedEmail: { type: String, default: "" },
	verified: { type: Boolean, default: false },
	verifiedEmail: { type: String, default: "" },
	posProfile: { type: String, default: "" },
});

const emit = defineEmits(["verified", "lock-change"]);

const DEFAULT_TTL = 900;
const DEFAULT_COOLDOWN = 60;
const FABRICATED_SUFFIX = "@pos.miraaya";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const SEND_URL = "pos_next.api.email_verification.send_email_otp";
const VERIFY_URL = "pos_next.api.email_verification.verify_email_otp";

const state = ref("idle");
const returnState = ref("idle");
const otp = ref("");
const errorMessage = ref("");
const infoMessage = ref("");
const now = ref(Date.now());
const expiresAt = ref(0);
const cooldownUntil = ref(0);
const offline = ref(Boolean(isOffline()));
const justVerifiedEmail = ref("");
const otpInput = ref(null);
let timer = null;

const norm = (v) => (v || "").trim().toLowerCase();

const emailUsable = computed(() => {
	const e = (props.email || "").trim();
	return Boolean(e) && EMAIL_RE.test(e) && !norm(e).endsWith(FABRICATED_SUFFIX);
});
const emailDirty = computed(() => norm(props.email) !== norm(props.savedEmail));

const effectiveVerifiedEmail = computed(() => justVerifiedEmail.value || props.verifiedEmail);
const isVerified = computed(
	() =>
		(Boolean(justVerifiedEmail.value) || props.verified) &&
		Boolean(effectiveVerifiedEmail.value) &&
		norm(effectiveVerifiedEmail.value) === norm(props.email)
);
const verifiedEmailShown = computed(() => effectiveVerifiedEmail.value);

/** The step shown to the cashier (error overlays the previous step). */
const view = computed(() => {
	const current = state.value === "error" ? returnState.value : state.value;
	if (current === "idle" && isVerified.value) return "verified";
	if (current === "verifying") return "code_sent";
	return current;
});

const canSend = computed(
	() => emailUsable.value && !emailDirty.value && !offline.value && Boolean(props.customer)
);
const otpComplete = computed(() => /^\d{6}$/.test(otp.value));
const remainingSeconds = computed(() =>
	Math.max(0, Math.ceil((expiresAt.value - now.value) / 1000))
);
const cooldownRemaining = computed(() =>
	Math.max(0, Math.ceil((cooldownUntil.value - now.value) / 1000))
);
const countdownLabel = computed(() => {
	const s = remainingSeconds.value;
	return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
});

const locked = computed(() => {
	const current = state.value === "error" ? returnState.value : state.value;
	return ["sending", "code_sent", "verifying"].includes(current);
});

watch(locked, (value) => emit("lock-change", value), { immediate: true });

function setState(next) {
	if (next !== "error") returnState.value = next;
	state.value = next;
}

function fail(message, keep) {
	// keep: state to stay on while showing the error
	returnState.value = keep;
	state.value = "error";
	errorMessage.value = message;
}

function startTimer() {
	stopTimer();
	now.value = Date.now();
	timer = setInterval(tick, 1000);
}
function stopTimer() {
	if (timer) clearInterval(timer);
	timer = null;
}
function tick() {
	now.value = Date.now();
	const active = state.value === "error" ? returnState.value : state.value;
	if (active === "code_sent" && remainingSeconds.value <= 0) {
		stopTimer();
		otp.value = "";
		errorMessage.value = "";
		setState("expired");
	} else if (active !== "code_sent" && cooldownRemaining.value <= 0) {
		stopTimer();
	}
}

function messageFrom(res, fallback) {
	return res?.message || fallback;
}

function unwrap(response) {
	return response?.message && typeof response.message === "object" ? response.message : response;
}

function exceptionMessage(err) {
	return (
		err?.messages?.[0] ||
		err?.message ||
		(typeof err === "string" ? err : null) ||
		__("Could not send the code, please try again.")
	);
}

async function sendCode() {
	if (!canSend.value || state.value === "sending" || state.value === "verifying") return;
	if (state.value === "code_sent" && cooldownRemaining.value > 0) return;
	const previous = state.value === "error" ? returnState.value : state.value;
	errorMessage.value = "";
	infoMessage.value = "";
	setState("sending");
	try {
		const res = unwrap(
			await call(SEND_URL, {
				customer: props.customer,
				email: props.email.trim(),
				pos_profile: props.posProfile || undefined,
			})
		);
		if (res?.ok && res.code === "otp_not_required") {
			infoMessage.value = messageFrom(res, "");
			setState("idle");
			return;
		}
		if (res?.ok) {
			const ttl = Number(res.expires_in) || DEFAULT_TTL;
			const cooldown = Math.max(Number(res.resend_in) || 0, DEFAULT_COOLDOWN);
			now.value = Date.now();
			expiresAt.value = now.value + ttl * 1000;
			cooldownUntil.value = now.value + cooldown * 1000;
			otp.value = "";
			setState("code_sent");
			startTimer();
			await nextTick();
			otpInput.value?.focus?.();
			return;
		}
		if (res?.retry_after) {
			now.value = Date.now();
			cooldownUntil.value = now.value + Number(res.retry_after) * 1000;
			startTimer();
		}
		const keep = previous === "code_sent" ? "code_sent" : previous === "expired" ? "expired" : "idle";
		fail(messageFrom(res, __("Could not send the code, please try again.")), keep);
	} catch (err) {
		fail(exceptionMessage(err), previous === "code_sent" ? "code_sent" : "idle");
	}
}

async function verify() {
	if (!otpComplete.value || state.value === "verifying" || offline.value) return;
	errorMessage.value = "";
	state.value = "verifying";
	try {
		const res = unwrap(
			await call(VERIFY_URL, {
				customer: props.customer,
				otp: otp.value,
				email: props.email.trim(),
				pos_profile: props.posProfile || undefined,
			})
		);
		if (res?.ok === true && res.code === "verified") {
			stopTimer();
			otp.value = "";
			justVerifiedEmail.value = res.verified_email || props.email.trim();
			// The verified badge is derived from the idle view + matching email
			setState("idle");
			emit("verified", { customer: props.customer, verified_email: justVerifiedEmail.value });
			return;
		}
		if (res?.code === "expired") {
			stopTimer();
			otp.value = "";
			setState("expired");
			return;
		}
		if (res?.retry_after) {
			now.value = Date.now();
			cooldownUntil.value = now.value + Number(res.retry_after) * 1000;
		}
		fail(messageFrom(res, __("Wrong code (or email changed).")), "code_sent");
	} catch (err) {
		fail(exceptionMessage(err), "code_sent");
	}
}

function onOtpInput() {
	otp.value = (otp.value || "").replace(/\D/g, "").slice(0, 6);
	if (state.value === "error") {
		errorMessage.value = "";
		state.value = returnState.value;
	}
}

function changeEmail() {
	stopTimer();
	otp.value = "";
	errorMessage.value = "";
	setState("idle");
}

function reset() {
	stopTimer();
	otp.value = "";
	errorMessage.value = "";
	infoMessage.value = "";
	justVerifiedEmail.value = "";
	setState("idle");
}

// Editing the email (when not locked) clears any "just verified" badge.
watch(
	() => props.email,
	(value) => {
		if (justVerifiedEmail.value && norm(value) !== norm(justVerifiedEmail.value)) {
			justVerifiedEmail.value = "";
		}
		if (state.value === "expired") setState("idle");
		infoMessage.value = "";
	}
);
watch(
	() => props.customer,
	() => reset()
);

const syncOffline = () => {
	offline.value = Boolean(isOffline());
};
onMounted(() => {
	syncOffline();
	window.addEventListener("online", syncOffline);
	window.addEventListener("offline", syncOffline);
});
onBeforeUnmount(() => {
	stopTimer();
	window.removeEventListener("online", syncOffline);
	window.removeEventListener("offline", syncOffline);
});

defineExpose({ state, view, reset });
</script>
