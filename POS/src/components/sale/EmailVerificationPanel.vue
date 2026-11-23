<template>
	<div class="rounded-xl border border-gray-200 bg-pos-panel p-3" data-testid="email-verification-panel">
		<!-- Verified badge (idle view only; stays correct while the email is unchanged) -->
		<div
			v-if="view === 'verified'"
			class="flex flex-wrap items-center gap-x-2 gap-y-1 text-pos-sm text-pos-saving"
			data-testid="verified-badge"
		>
			<svg class="h-4 w-4 flex-shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
				<path d="M5 12l5 5L20 7" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
			<span class="font-semibold">{{ __("Email verified") }}</span>
			<span class="min-w-0 break-all text-xs" dir="ltr">{{ verifiedEmailShown }}</span>
		</div>

		<!-- idle / expired -->
		<div v-else-if="view === 'idle' || view === 'expired'" class="flex flex-col gap-2">
			<div class="flex flex-wrap items-center justify-between gap-2">
				<span class="text-pos-sm text-pos-muted" data-testid="not-verified-label">
					{{ __("Email not verified") }}
				</span>
				<button
					type="button"
					:class="actionButton"
					data-testid="send-code"
					:disabled="!canSend"
					@click="sendCode"
				>
					{{ view === "expired" ? __("Send new code by email") : __("Verify email") }}
				</button>
			</div>
			<p v-if="view === 'expired'" class="text-xs text-pos-caution" data-testid="expired-msg">
				{{ __("Code expired. Request a new one.") }}
			</p>
			<p v-if="offline" class="text-xs text-pos-muted" data-testid="offline-msg">
				{{ __("Verification requires an internet connection.") }}
			</p>
			<p v-else-if="!emailUsable" class="text-xs text-pos-muted">
				{{ __("Enter a valid email address.") }}
			</p>
			<div
				v-else-if="emailDirty"
				class="flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 pt-2"
				data-testid="unsaved-msg"
			>
				<p class="text-xs text-pos-muted">
					{{ __("Save the customer's email before verifying it.") }}
				</p>
				<button
					type="button"
					:class="actionButton"
					data-testid="save-and-send"
					:disabled="!customer"
					@click="emit('save-and-send')"
				>
					{{ __("Save email & send code") }}
				</button>
			</div>
		</div>

		<!-- sending -->
		<div
			v-else-if="view === 'sending'"
			class="flex min-h-target items-center gap-2 text-pos-sm text-pos-muted"
			data-testid="sending"
		>
			<span class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-pos-action" />
			{{ __("Sending code…") }}
		</div>

		<!-- code_sent / verifying -->
		<div v-else class="flex flex-col gap-2">
			<p class="text-pos-sm text-pos-ink" data-testid="enter-code-hint">
				{{ __("Enter the 6-digit code sent to the email {0}", [email]) }}
			</p>
			<div class="flex flex-wrap items-center gap-2">
				<input
					ref="otpInput"
					v-model="otp"
					type="text"
					inputmode="numeric"
					autocomplete="one-time-code"
					maxlength="6"
					dir="ltr"
					class="min-h-target w-44 rounded-lg border border-gray-300 bg-white px-3 text-center text-pos-lg font-semibold tabular-nums tracking-[0.35em] placeholder:text-pos-sm placeholder:font-normal placeholder:tracking-normal focus:border-pos-action focus:outline-none focus:ring-1 focus:ring-pos-action"
					data-testid="otp-input"
					:placeholder="__('Verification code')"
					:disabled="state === 'verifying'"
					@input="onOtpInput"
					@keydown.enter.prevent="verify"
				/>
				<button
					type="button"
					:class="actionButton"
					data-testid="verify"
					:disabled="!otpComplete || state === 'verifying' || offline"
					@click="verify"
				>
					<span v-if="state === 'verifying'" data-testid="verifying">{{ __("Verifying email…") }}</span>
					<span v-else>{{ __("Verify") }}</span>
				</button>
			</div>
			<div class="flex flex-wrap items-center justify-between gap-x-3 text-xs text-pos-muted">
				<span class="tabular-nums" data-testid="countdown">{{ __("Code expires in {0}", [countdownLabel]) }}</span>
				<div class="flex flex-wrap items-center">
					<button
						type="button"
						:class="linkButton"
						data-testid="resend"
						:disabled="cooldownRemaining > 0 || state === 'verifying' || offline"
						@click="sendCode"
					>
						<template v-if="cooldownRemaining > 0">
							{{ __("Resend available in {0}s", [cooldownRemaining]) }}
						</template>
						<template v-else>{{ __("Resend code by email") }}</template>
					</button>
					<button
						type="button"
						:class="linkButton"
						data-testid="change-email"
						:disabled="state === 'verifying'"
						@click="changeEmail"
					>
						{{ __("Change email") }}
					</button>
				</div>
			</div>
		</div>

		<p v-if="state === 'error' && errorMessage" class="mt-2 text-xs text-pos-danger" data-testid="error-msg" role="alert">
			{{ errorMessage }}
		</p>
		<p v-if="infoMessage" class="mt-2 text-xs text-pos-muted" data-testid="info-msg">{{ infoMessage }}</p>
	</div>
</template>

<script setup>
/**
 * EmailVerificationPanel - cashier-initiated email OTP verification.
 *
 * States: idle | sending | code_sent | verifying | verified | expired | error
 * `error` keeps the previous step visible (see returnState).
 * The code is delivered by email only. Nothing about the code is persisted
 * client side; the server owns the phone
 * number (taken from Customer.mobile_no) and all rate limits. Message text
 * comes from the server result; the panel adds no provider wording.
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

const emit = defineEmits(["verified", "lock-change", "save-and-send"]);

// Touch-sized controls (min-h-target is 40px, 44px on tablets and phones)
const actionButton =
	"inline-flex min-h-target items-center justify-center rounded-lg bg-pos-action px-4 text-pos-sm font-semibold text-white hover:bg-pos-action-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-pos-action focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-gray-300";
const linkButton =
	"inline-flex min-h-target items-center px-2 text-xs font-medium text-pos-action hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-pos-action disabled:cursor-not-allowed disabled:text-gray-400 disabled:no-underline";

const DEFAULT_TTL = 900;
const DEFAULT_COOLDOWN = 60;
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
	return Boolean(e) && EMAIL_RE.test(e);
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

// Verify results after which the entered code is no longer usable from this panel.
// ("busy" is refused before the code is used: stay on the code step and retry.)
const LEAVE_CODE_SENT = new Set(["email_in_use", "verification_not_saved"]);

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
		if (LEAVE_CODE_SENT.has(res?.code)) {
			// Email verified elsewhere, or the code was used but not saved:
			// this code cannot be retried. Start over.
			stopTimer();
			otp.value = "";
			fail(messageFrom(res, __("Could not verify the code, please try again.")), "idle");
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
	// Arabic-Indic (U+0660-0669) and Eastern Arabic-Indic (U+06F0-06F9) digits become ASCII first
	otp.value = (otp.value || "")
		.replace(/[\u0660-\u0669\u06F0-\u06F9]/g, (d) => String(d.charCodeAt(0) & 0xf))
		.replace(/\D/g, "")
		.slice(0, 6);
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

defineExpose({ state, view, reset, send: sendCode });
</script>
