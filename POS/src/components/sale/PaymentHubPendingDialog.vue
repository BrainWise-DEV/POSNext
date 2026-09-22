<template>
	<Dialog v-model="show" :options="{ title: __('Payment Hub'), size: '2xl' }">
		<template #body-content>
			<div class="space-y-3">
				<!-- Main views -->
				<div class="grid grid-cols-3 gap-2">
					<button
						v-for="view in views"
						:key="view.key"
						@click="activeView = view.key"
						:class="[
							'rounded-lg border px-2 py-2 text-xs sm:text-sm font-semibold transition-colors',
							activeView === view.key
								? 'border-blue-500 bg-blue-50 text-blue-700'
								: 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50',
						]"
					>
						{{ __(view.label) }}
					</button>
				</div>


				<!-- Profile / shift scope -->
				<div class="rounded-lg border border-gray-200 bg-gray-50 p-2.5">
					<div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
						<div>
							<label class="mb-1 block text-[10px] font-semibold uppercase text-gray-500">{{ __('POS Profile') }}</label>
							<select
								v-if="scopeContext.can_view_all_profiles"
								v-model="selectedProfile"
								@change="handleProfileChange"
								class="h-8 w-full rounded-lg border border-gray-300 bg-white px-2 text-xs"
							>
								<option value="__all__">{{ __('All POS Profiles') }}</option>
								<option v-for="profile in scopeContext.profiles || []" :key="profile" :value="profile">{{ profile }}</option>
							</select>
							<div v-else class="flex h-8 items-center rounded-lg border border-gray-200 bg-white px-2 text-xs font-semibold text-gray-700">
								{{ selectedProfile || props.posProfile || '-' }}
							</div>
						</div>

						<div v-if="showScopeFilter">
							<label class="mb-1 block text-[10px] font-semibold uppercase text-gray-500">{{ __('Period') }}</label>
							<select v-model="selectedScope" @change="handleScopeChange" class="h-8 w-full rounded-lg border border-gray-300 bg-white px-2 text-xs">
								<option v-for="option in scopeOptions" :key="option" :value="option">{{ __(option) }}</option>
							</select>
						</div>

						<div v-if="showCustomDates" class="grid grid-cols-2 gap-1">
							<div><label class="mb-1 block text-[10px] font-semibold uppercase text-gray-500">{{ __('From') }}</label><input v-model="customFromDate" @change="handleScopeChange" type="date" class="h-8 w-full rounded-lg border border-gray-300 bg-white px-1 text-xs" /></div>
							<div><label class="mb-1 block text-[10px] font-semibold uppercase text-gray-500">{{ __('To') }}</label><input v-model="customToDate" @change="handleScopeChange" type="date" class="h-8 w-full rounded-lg border border-gray-300 bg-white px-1 text-xs" /></div>
						</div>
						<div v-else-if="showScopeFilter">
							<label class="mb-1 block text-[10px] font-semibold uppercase text-gray-500">{{ __('Scope') }}</label>
							<div class="flex h-8 items-center rounded-lg border border-gray-200 bg-white px-2 text-[11px] text-gray-600">{{ scopeDescription }}</div>
						</div>
						<div v-else class="sm:col-span-2">
							<label class="mb-1 block text-[10px] font-semibold uppercase text-gray-500">{{ activeQueue === 'Paid' ? __('Paid / Ready Queue') : __('Waiting Queue') }}</label>
							<div class="flex h-8 items-center rounded-lg border border-amber-200 bg-amber-50 px-2 text-[11px] text-amber-800">
								{{ activeQueue === 'Paid'
									? __('Captured payments stay visible across shift changes until the invoice is completed in an open shift.')
									: __('All unresolved payments for this profile within the {0}-hour recovery window', [recoveryHours]) }}
							</div>
						</div>
					</div>
				</div>

				<!-- QUEUES -->
				<template v-if="activeView === 'Queues'">
					<div class="grid grid-cols-3 gap-2">
						<button
							v-for="tab in queueTabs"
							:key="tab.key"
							@click="activeQueue = tab.key"
							:class="[
								'rounded-lg border px-3 py-2 text-sm font-semibold transition-colors',
								activeQueue === tab.key
									? tab.activeClass
									: 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50',
							]"
						>
							{{ __(tab.label) }}
							<span class="ms-1 rounded-full bg-black/10 px-1.5 py-0.5 text-xs">
								{{ counts[tab.countKey] || 0 }}
							</span>
						</button>
					</div>

					<div class="flex gap-2">
						<input
							v-model="queueSearch"
							type="text"
							class="h-9 flex-1 rounded-lg border border-gray-300 px-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
							:placeholder="__('Search session, customer, mobile or invoice')"
							@keyup.enter="refreshQueues"
						/>
						<button @click="refreshQueues" :disabled="loading" class="h-9 rounded-lg bg-gray-800 px-4 text-sm font-semibold text-white disabled:opacity-50">
							{{ loading ? __('Loading...') : __('Refresh') }}
						</button>
					</div>

					<div v-if="activeQueue === 'Waiting' || activeQueue === 'Failed'" class="flex items-center justify-end gap-2 text-[11px] text-gray-600">
						<span>{{ __('Draft Print') }}:</span>
						<select v-model="draftPrintType" class="h-8 rounded-lg border border-gray-300 bg-white px-2 text-xs">
							<option value="Receipt">{{ __('Receipt / Thermal') }}</option>
							<option value="A4">{{ __('A4') }}</option>
						</select>
					</div>

					<div v-if="loading && queueRows.length === 0" class="py-10 text-center text-sm text-gray-500">
						{{ __('Loading Payment Hub sales...') }}
					</div>
					<div v-else-if="queueRows.length === 0" class="rounded-lg border border-dashed border-gray-300 py-10 text-center text-sm text-gray-500">
						{{ __('No sales in this queue') }}
					</div>
					<div v-else class="max-h-[55vh] space-y-2 overflow-y-auto pe-1">
						<div v-for="row in queueRows" :key="row.name" class="rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
							<div class="flex flex-wrap items-start justify-between gap-2">
								<div>
									<div class="font-semibold text-gray-900">{{ row.name }}</div>
									<div class="mt-0.5 text-xs text-gray-500">
										{{ row.customer_name || row.customer || __('Walk-in Customer') }}
										<span v-if="row.mobile_number"> · {{ row.mobile_number }}</span>
									</div>
									<div v-if="row.provider" class="mt-1 text-[11px] text-blue-600">
										{{ row.provider }}<span v-if="row.actual_payment_method"> · {{ row.actual_payment_method }}</span>
									</div>
									<div class="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-gray-400">
										<span v-if="row.pos_profile">{{ row.pos_profile }}</span>
										<span v-if="row.pos_opening_shift">· {{ row.pos_opening_shift }}</span>
										<span v-if="row.cashier_user">· {{ row.cashier_user }}</span>
										<span v-if="row.is_previous_shift" class="rounded-full bg-amber-100 px-1.5 py-0.5 font-semibold text-amber-700">{{ __('Previous Shift') }}</span>
									</div>
								</div>
								<div class="text-end">
									<div class="text-base font-bold text-gray-900">{{ formatAmount(row.grand_total, row.currency) }}</div>
									<div class="text-xs font-medium" :class="statusClass(row.status)">{{ __(row.status) }}</div>
								</div>
							</div>

							<div class="mt-2 grid grid-cols-3 gap-2 rounded-lg bg-gray-50 p-2 text-center text-xs">
								<div><div class="text-gray-500">{{ __('Paid') }}</div><div class="font-semibold">{{ formatAmount(row.confirmed_paid_amount, row.currency) }}</div></div>
								<div><div class="text-gray-500">{{ __('Pending') }}</div><div class="font-semibold">{{ formatAmount(row.pending_amount, row.currency) }}</div></div>
								<div><div class="text-gray-500">{{ __('Remaining') }}</div><div class="font-semibold">{{ formatAmount(row.remaining_amount, row.currency) }}</div></div>
							</div>

							<div v-if="row.electronic_allocation" class="mt-2 rounded-lg border border-gray-200 bg-white p-2.5">
								<div class="flex flex-wrap items-start justify-between gap-2">
									<div>
										<div class="text-[10px] font-bold uppercase tracking-wide text-gray-500">{{ __('Electronic Payment Attempt') }}</div>
										<div class="mt-0.5 text-xs font-semibold text-gray-800">
											{{ row.electronic_mode_of_payment || __('Electronic Payment') }}
											<span v-if="row.provider"> · {{ row.provider }}</span>
											<span v-if="row.actual_payment_method"> · {{ row.actual_payment_method }}</span>
										</div>
										<div class="mt-0.5 text-[10px] text-gray-400">
											{{ row.electronic_allocation }}
											<span v-if="row.gateway_transaction"> · {{ row.gateway_transaction }}</span>
										</div>
									</div>
									<div class="text-end">
										<div class="text-xs font-bold text-gray-900">{{ formatAmount(row.electronic_amount, row.currency) }}</div>
										<span :class="electronicStatusClass(row)" class="mt-1 inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold uppercase">
											{{ electronicStatusLabel(row) }}
										</span>
									</div>
								</div>
								<div v-if="row.provider_message" class="mt-1.5 text-[11px] text-gray-600">{{ row.provider_message }}</div>
								<div v-if="row.can_resend_link" class="mt-1.5 text-[11px] font-medium text-blue-700">
									{{ __('Provider still reports this payment attempt as pending. Check Status before retrying; resend only while the stored link lifetime is still active.') }}
								</div>
								<div v-else-if="row.can_create_new_link" class="mt-1.5 rounded-md border border-red-100 bg-red-50 px-2 py-1 text-[11px] font-medium text-red-700">
									{{ row.link_expired ? __('Stored payment-link lifetime has ended. Create a new link after the final provider status check.') : __('Previous payment attempt is closed. Create a new payment link for the unpaid balance.') }}
								</div>
								<div v-if="row.electronic_expires_at" class="mt-1 text-[10px] text-gray-400">
									{{ __('Link expiry') }}: {{ formatDateTime(row.electronic_expires_at) }}
								</div>
							</div>

							<div v-if="activeQueue === 'Waiting' && row.link_send_count > 0" class="mt-2 text-[11px] text-gray-500">
								{{ __('WhatsApp attempt {0}', [row.link_send_count]) }}
								<span v-if="row.link_sent_at"> · {{ formatDateTime(row.link_sent_at) }}</span>
								<span v-if="row.whatsapp_status"> · {{ __(row.whatsapp_status) }}</span>
							</div>
							<div v-if="row.last_error" class="mt-2 rounded-md border border-red-100 bg-red-50 px-2 py-1.5 text-[11px] text-red-700 break-words">
								{{ row.last_error }}
							</div>
							<div v-if="row.recover_until && activeQueue !== 'Paid'" class="mt-1 text-[10px] text-gray-400">
								{{ __('Recoverable until') }} {{ formatDateTime(row.recover_until) }}
							</div>
							<div v-if="row.session_closed" class="mt-2 rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-[11px] font-medium text-gray-600">
								{{ row.status === 'Expired'
									? __('Recovery expired. Start a new sale to create another payment request.')
									: __('This Payment Hub session is closed. No new payment link can be created from this sale.') }}
							</div>

							<div class="mt-3 flex flex-wrap justify-end gap-2">
								<button v-if="row.payment_url" @click="copyPaymentLink(row)" :disabled="actionName === row.name" class="rounded-lg border border-violet-200 bg-violet-50 px-3 py-1.5 text-xs font-semibold text-violet-700 disabled:opacity-50">
									{{ __('Copy Link') }}
								</button>
								<button v-if="row.can_resend_link" @click="resend(row)" :disabled="actionName === row.name" class="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 disabled:opacity-50">
									{{ row.link_send_count > 0 ? __('Resend Link + WhatsApp') : __('Send Link + WhatsApp') }}
								</button>
								<button v-if="(activeQueue === 'Waiting' || activeQueue === 'Failed') && row.electronic_allocation" @click="checkPayment(row)" :disabled="actionName === row.name" class="rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
									{{ actionName === row.name ? __('Checking...') : __('Check Status') }}
								</button>
								<button v-if="activeQueue === 'Waiting' || activeQueue === 'Failed'" @click="printDraft(row)" :disabled="actionName === row.name" class="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 disabled:opacity-50">
									{{ __('Print Unpaid Draft') }}
								</button>
								<button v-if="row.can_create_new_link" @click="newPaymentLink(row, false)" :disabled="actionName === row.name" class="rounded-lg border border-blue-300 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 disabled:opacity-50">
									{{ __('Create New Link') }}
								</button>
								<button v-if="row.can_create_new_link" @click="newPaymentLink(row, true)" :disabled="actionName === row.name" class="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
									{{ actionName === row.name ? __('Creating...') : __('New Link + WhatsApp') }}
								</button>
								<button v-if="activeQueue === 'Paid'" @click="completeAndPrint(row)" :disabled="actionName === row.name || !props.posOpeningShift || (props.posProfile && row.pos_profile && row.pos_profile !== props.posProfile)" class="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
									{{ !props.posOpeningShift
										? __('Open Shift Required')
										: ((props.posProfile && row.pos_profile && row.pos_profile !== props.posProfile)
											? __('Open Matching POS Profile')
											: (actionName === row.name ? __('Completing...') : __('Complete & Print'))) }}
								</button>
							</div>
						</div>
					</div>
				</template>

				<!-- TRANSACTION HISTORY -->
				<template v-else-if="activeView === 'History'">
					<div class="rounded-lg border border-blue-100 bg-blue-50 p-3 text-xs text-blue-800">
						{{ __('Search a customer payment or refund by mobile number, customer, invoice, return invoice, Payment Hub transaction or provider transaction/refund ID.') }}
					</div>
					<div class="flex gap-2">
						<input v-model="historySearch" type="text" class="h-9 flex-1 rounded-lg border border-gray-300 px-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500" :placeholder="__('Mobile, invoice, customer, transaction or refund ID')" @keyup.enter="loadHistory" />
						<button @click="loadHistory" :disabled="historyLoading" class="h-9 rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white disabled:opacity-50">{{ historyLoading ? __('Searching...') : __('Search') }}</button>
					</div>
					<div class="flex flex-wrap justify-end gap-2">
						<button @click="exportHistory('xlsx')" :disabled="historyRows.length === 0" class="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 disabled:cursor-not-allowed disabled:opacity-40">{{ __('Export Excel') }}</button>
						<button @click="exportHistory('pdf')" :disabled="historyRows.length === 0" class="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 disabled:cursor-not-allowed disabled:opacity-40">{{ __('Export PDF') }}</button>
					</div>
					<div v-if="historyLoading && historyRows.length === 0" class="py-10 text-center text-sm text-gray-500">{{ __('Loading transaction history...') }}</div>
					<div v-else-if="historyRows.length === 0" class="rounded-lg border border-dashed border-gray-300 py-10 text-center text-sm text-gray-500">{{ __('No transactions found') }}</div>
					<div v-else class="max-h-[58vh] space-y-2 overflow-y-auto pe-1">
						<div v-for="(row, index) in historyRows" :key="historyKey(row, index)" class="rounded-lg border border-gray-200 bg-white p-3">
							<div class="flex items-start justify-between gap-3">
								<div class="min-w-0">
									<div class="flex flex-wrap items-center gap-2">
										<span :class="historyTypeClass(row.transaction_type)" class="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase">{{ __(row.transaction_type) }}</span>
										<span class="text-sm font-bold text-gray-900">{{ row.return_invoice || row.invoice || row.session || row.gateway_transaction }}</span>
									</div>
									<div class="mt-1 text-xs text-gray-500">{{ row.customer_name || row.customer || __('Walk-in Customer') }}<span v-if="row.mobile_number"> · {{ row.mobile_number }}</span></div>
									<div class="mt-1 text-[11px] text-gray-600">{{ row.mode_of_payment || row.channel || '-' }}<span v-if="row.provider"> · {{ row.provider }}</span><span v-if="row.actual_payment_method"> · {{ row.actual_payment_method }}</span></div>
									<div class="mt-1 text-[10px] text-gray-400">{{ formatDateTime(row.transaction_datetime) }}<span v-if="row.gateway_transaction"> · {{ row.gateway_transaction }}</span></div>
									<div v-if="row.provider_refund_id || row.provider_transaction_id" class="mt-1 break-all text-[10px] text-gray-500">
										{{ row.provider_refund_id ? __('Refund ID:') : __('Provider Transaction:') }} {{ row.provider_refund_id || row.provider_transaction_id }}
									</div>
									<div v-if="row.is_override" class="mt-1 text-[10px] font-semibold text-orange-700">{{ __('Refund override') }} · {{ __('Authorized by') }} {{ row.authorized_by || '-' }}<span v-if="row.override_reason"> · {{ row.override_reason }}</span></div>
								</div>
								<div class="flex-shrink-0 text-end">
									<div :class="row.transaction_type === 'Refund' ? 'text-red-600' : 'text-gray-900'" class="text-base font-bold">{{ row.transaction_type === 'Refund' ? '-' : '' }}{{ formatAmount(row.amount, row.currency) }}</div>
									<div class="text-xs font-semibold" :class="statusClass(row.status)">{{ __(row.status || '-') }}</div>
									<div v-if="row.remaining_refundable !== null && row.remaining_refundable !== undefined" class="mt-1 text-[10px] text-blue-600">{{ __('Refundable:') }} {{ formatAmount(row.remaining_refundable, row.currency) }}</div>
								</div>
							</div>
						</div>
					</div>
				</template>

				<!-- DAILY REPORT -->
				<template v-else>
					<div class="flex justify-end">
						<button @click="loadDailyReport" :disabled="reportLoading" class="h-9 rounded-lg bg-gray-800 px-4 text-sm font-semibold text-white disabled:opacity-50">{{ reportLoading ? __('Loading...') : __('Refresh Report') }}</button>
					</div>

					<div class="flex flex-wrap justify-end gap-2">
						<button @click="exportDailyReport('xlsx')" :disabled="dailyReport.rows.length === 0" class="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 disabled:cursor-not-allowed disabled:opacity-40">{{ __('Export Excel') }}</button>
						<button @click="exportDailyReport('pdf')" :disabled="dailyReport.rows.length === 0" class="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 disabled:cursor-not-allowed disabled:opacity-40">{{ __('Export PDF') }}</button>
					</div>

					<div class="grid grid-cols-3 gap-2">
						<div class="rounded-lg border border-green-200 bg-green-50 p-3 text-center"><div class="text-[10px] font-semibold uppercase text-green-700">{{ __('Payments') }}</div><div class="mt-1 text-sm sm:text-lg font-bold text-green-900">{{ formatAmount(dailyReport.payment_total, dailyReport.currency) }}</div></div>
						<div class="rounded-lg border border-red-200 bg-red-50 p-3 text-center"><div class="text-[10px] font-semibold uppercase text-red-700">{{ __('Refunds') }}</div><div class="mt-1 text-sm sm:text-lg font-bold text-red-900">{{ formatAmount(dailyReport.refund_total, dailyReport.currency) }}</div></div>
						<div class="rounded-lg border border-blue-200 bg-blue-50 p-3 text-center"><div class="text-[10px] font-semibold uppercase text-blue-700">{{ __('Net Collection') }}</div><div class="mt-1 text-sm sm:text-lg font-bold text-blue-900">{{ formatAmount(dailyReport.net_total, dailyReport.currency) }}</div></div>
					</div>

					<div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
						<div class="rounded-lg border border-gray-200 p-3"><div class="mb-2 text-xs font-bold text-gray-700">{{ __('By Payment Channel') }}</div><div v-for="item in dailyReport.channel_summary" :key="item.name" class="grid grid-cols-4 gap-1 border-t border-gray-100 py-1.5 text-[11px]"><div class="font-semibold text-gray-700">{{ __(item.name) }}</div><div class="text-end">{{ formatAmount(item.payments, dailyReport.currency) }}</div><div class="text-end text-red-600">-{{ formatAmount(item.refunds, dailyReport.currency) }}</div><div class="text-end font-bold">{{ formatAmount(item.net, dailyReport.currency) }}</div></div></div>
						<div class="rounded-lg border border-gray-200 p-3"><div class="mb-2 text-xs font-bold text-gray-700">{{ __('By Provider') }}</div><div v-for="item in dailyReport.provider_summary" :key="item.name" class="grid grid-cols-4 gap-1 border-t border-gray-100 py-1.5 text-[11px]"><div class="font-semibold text-gray-700">{{ item.name }}</div><div class="text-end">{{ formatAmount(item.payments, dailyReport.currency) }}</div><div class="text-end text-red-600">-{{ formatAmount(item.refunds, dailyReport.currency) }}</div><div class="text-end font-bold">{{ formatAmount(item.net, dailyReport.currency) }}</div></div></div>
					</div>

					<div v-if="reportLoading && dailyReport.rows.length === 0" class="py-8 text-center text-sm text-gray-500">{{ __('Loading report...') }}</div>
					<div v-else-if="dailyReport.rows.length === 0" class="rounded-lg border border-dashed border-gray-300 py-8 text-center text-sm text-gray-500">{{ __('No paid/refund transactions for this period') }}</div>
					<div v-else class="max-h-[38vh] overflow-y-auto rounded-lg border border-gray-200">
						<div v-for="(row, index) in dailyReport.rows" :key="historyKey(row, index)" class="grid grid-cols-[1fr_auto] gap-2 border-b border-gray-100 p-2 text-xs last:border-b-0">
							<div><div class="font-semibold text-gray-800">{{ row.return_invoice || row.invoice }} · {{ __(row.transaction_type) }}</div><div class="text-[10px] text-gray-500">{{ row.mode_of_payment }}<span v-if="row.provider"> · {{ row.provider }}</span> · {{ row.customer_name || row.customer || '-' }}</div></div>
							<div class="text-end"><div :class="row.transaction_type === 'Refund' ? 'text-red-600' : 'text-green-700'" class="font-bold">{{ row.transaction_type === 'Refund' ? '-' : '' }}{{ formatAmount(row.amount, row.currency) }}</div><div class="text-[10px] text-gray-500">{{ __(row.status) }}</div></div>
						</div>
					</div>
				</template>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { Dialog } from "frappe-ui"
import { computed, onUnmounted, ref, watch } from "vue"
import { call } from "@/utils/apiWrapper"
import { useToast } from "@/composables/useToast"

const props = defineProps({
	modelValue: Boolean,
	posProfile: { type: String, default: null },
	posOpeningShift: { type: String, default: null },
	paymentHubConfig: { type: Object, default: null },
})

const emit = defineEmits(["update:modelValue", "completed", "counts-updated"])
const { showSuccess, showWarning } = useToast()

const show = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
})

const views = [
	{ key: "Queues", label: "Sales Queues" },
	{ key: "History", label: "Transaction History" },
	{ key: "Daily", label: "Daily Report" },
]
const queueTabs = [
	{ key: "Waiting", label: "Waiting", countKey: "waiting", activeClass: "border-amber-400 bg-amber-50 text-amber-700" },
	{ key: "Paid", label: "Paid", countKey: "paid", activeClass: "border-green-400 bg-green-50 text-green-700" },
	{ key: "Failed", label: "Failed", countKey: "failed", activeClass: "border-red-400 bg-red-50 text-red-700" },
]

const activeView = ref("Queues")
const activeQueue = ref("Waiting")
const queueRows = ref([])
const counts = ref({ waiting: 0, paid: 0, failed: 0 })
const loading = ref(false)
const actionName = ref(null)
const queueSearch = ref("")
const historySearch = ref("")
const historyRows = ref([])
const historyLoading = ref(false)
const reportLoading = ref(false)
const dailyReport = ref(emptyDailyReport())
const scopeContext = ref({ can_view_all_profiles: false, profiles: [], today: localDateValue(), yesterday: localDateValue() })
const selectedProfile = ref(props.posProfile || "")
const selectedScope = ref("Today")
const customFromDate = ref(localDateValue())
const customToDate = ref(localDateValue())
const draftPrintType = ref("Receipt")
const scopeLoading = ref(false)
let refreshTimer = null

function emptyDailyReport() {
	return { currency: "KWD", payment_total: 0, refund_total: 0, net_total: 0, channel_summary: [], provider_summary: [], rows: [] }
}

function localDateValue() {
	const date = new Date()
	const pad = (value) => String(value).padStart(2, "0")
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

const recoveryHours = computed(() => Number(props.paymentHubConfig?.pending_sale_retention_hours || 24))
const showScopeFilter = computed(() => !(activeView.value === "Queues" && ["Waiting", "Paid"].includes(activeQueue.value)))
const showCustomDates = computed(() => showScopeFilter.value && selectedScope.value === "Custom Date Range")
const scopeOptions = computed(() => {
	const options = []
	if (scopeContext.value?.current_shift?.name && selectedProfile.value) options.push("Current Shift")
	if (scopeContext.value?.last_shift?.name && selectedProfile.value) options.push("Last Shift")
	options.push("Today", "Yesterday", "Custom Date Range")
	return options
})
const scopeDescription = computed(() => {
	if (selectedScope.value === "Current Shift") {
		const shift = scopeContext.value?.current_shift
		return shift?.name ? `${shift.name}${shift.business_date ? ` · ${shift.business_date}` : ""}` : __("Current Shift")
	}
	if (selectedScope.value === "Last Shift") {
		const shift = scopeContext.value?.last_shift
		return shift?.name ? `${shift.name}${shift.business_date ? ` · ${shift.business_date}` : ""}` : __("Last Shift")
	}
	if (selectedScope.value === "Today") return scopeContext.value?.today || localDateValue()
	if (selectedScope.value === "Yesterday") return scopeContext.value?.yesterday || localDateValue()
	return `${customFromDate.value} → ${customToDate.value}`
})

function scopeFilterArgs() {
	const args = {
		pos_profile: selectedProfile.value === "__all__" ? null : (selectedProfile.value || null),
		current_pos_profile: props.posProfile || null,
	}
	if (selectedScope.value === "Current Shift" && scopeContext.value?.current_shift?.name) {
		args.pos_opening_shift = scopeContext.value.current_shift.name
	} else if (selectedScope.value === "Last Shift" && scopeContext.value?.last_shift?.name) {
		args.pos_opening_shift = scopeContext.value.last_shift.name
	} else if (selectedScope.value === "Today") {
		args.from_date = scopeContext.value?.today || localDateValue()
		args.to_date = args.from_date
	} else if (selectedScope.value === "Yesterday") {
		args.from_date = scopeContext.value?.yesterday || localDateValue()
		args.to_date = args.from_date
	} else if (selectedScope.value === "Custom Date Range") {
		args.from_date = customFromDate.value || null
		args.to_date = customToDate.value || customFromDate.value || null
	}
	return args
}

async function loadScopeContext(resetScope = false) {
	scopeLoading.value = true
	try {
		const result = await call("erpnext_payment_hub.pos.api.get_payment_hub_pos_context", {
			current_pos_profile: props.posProfile || null,
			current_pos_opening_shift: props.posOpeningShift || null,
			selected_pos_profile: selectedProfile.value || null,
		})
		const context = unwrapPaymentHubResult(result) || {}
		scopeContext.value = context
		if (context.selected_pos_profile !== undefined && context.selected_pos_profile !== null) {
			selectedProfile.value = context.selected_pos_profile
		}
		if (!context.can_view_all_profiles && !selectedProfile.value) selectedProfile.value = props.posProfile || ""
		if (resetScope || !scopeOptions.value.includes(selectedScope.value)) {
			selectedScope.value = context.default_scope || "Today"
		}
		customFromDate.value = context.today || localDateValue()
		customToDate.value = context.today || localDateValue()
		const configured = props.paymentHubConfig?.default_draft_print_type
		draftPrintType.value = configured === "A4" ? "A4" : "Receipt"
	} catch (error) {
		scopeContext.value = { can_view_all_profiles: false, profiles: [], today: localDateValue(), yesterday: localDateValue() }
		selectedProfile.value = props.posProfile || ""
		selectedScope.value = props.posOpeningShift ? "Current Shift" : "Today"
	} finally {
		scopeLoading.value = false
	}
}

async function handleProfileChange() {
	if (selectedProfile.value === "__all__") selectedScope.value = "Today"
	await loadScopeContext(true)
	await refreshActiveView()
}

async function handleScopeChange() {
	await refreshActiveView()
}

async function refreshActiveView() {
	if (!show.value || scopeLoading.value) return
	if (activeView.value === "Queues") await refreshQueues()
	else if (activeView.value === "History") await loadHistory()
	else await loadDailyReport()
}

function unwrapPaymentHubResult(result) {
	return result?.message ?? result
}

function paymentHubErrorMessage(error, fallback) {
	const candidates = []
	if (error?.message) candidates.push(error.message)
	if (error?.exc) candidates.push(error.exc)
	if (error?._server_messages) {
		try {
			const messages = JSON.parse(error._server_messages)
			for (const item of messages || []) {
				try {
					const parsed = typeof item === "string" ? JSON.parse(item) : item
					if (parsed?.message) candidates.unshift(parsed.message)
				} catch {
					if (item) candidates.unshift(String(item))
				}
			}
		} catch {
			candidates.unshift(String(error._server_messages))
		}
	}
	const message = candidates.find((value) => String(value || "").trim())
	return message ? String(message).replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim() : fallback
}

function formatAmount(value, currency = "KWD") {
	return `${currency || "KWD"} ${Number(value || 0).toFixed(3)}`
}

function formatDateTime(value) {
	if (!value) return ""
	const parsed = new Date(String(value).replace(" ", "T"))
	return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString()
}

function statusClass(status) {
	const normalized = String(status || "").toLowerCase()
	if (["ready to complete", "completed", "captured", "refunded", "paid", "delivered", "read"].includes(normalized)) return "text-green-600"
	if (["failed", "expired", "cancelled", "manual review"].includes(normalized)) return "text-red-600"
	return "text-amber-600"
}

function electronicStatusLabel(row) {
	return row?.link_status || row?.provider_status || row?.electronic_status || __("Unknown")
}

function electronicStatusClass(row) {
	const normalized = String(electronicStatusLabel(row) || "").toLowerCase()
	if (["captured", "paid", "success", "successful"].includes(normalized)) return "bg-green-100 text-green-700"
	if (["failed", "expired", "cancelled", "canceled", "declined", "abandoned", "timedout", "timed out"].includes(normalized)) return "bg-red-100 text-red-700"
	return "bg-amber-100 text-amber-700"
}

function historyTypeClass(type) {
	if (type === "Refund") return "bg-red-100 text-red-700"
	if (type === "Pending Payment") return "bg-amber-100 text-amber-700"
	return "bg-green-100 text-green-700"
}

function historyKey(row, index) {
	return `${row.transaction_type}-${row.refund_allocation || row.source_allocation || row.gateway_transaction || row.return_invoice || row.invoice || row.session || index}-${index}`
}

async function loadCounts() {
	const result = await call("erpnext_payment_hub.pos.api.get_sales_queue_counts", {
		...scopeFilterArgs(),
		current_pos_opening_shift: props.posOpeningShift || null,
	})
	counts.value = unwrapPaymentHubResult(result) || { waiting: 0, paid: 0, failed: 0 }
	emit("counts-updated", counts.value)
}

async function loadQueueRows() {
	const result = await call("erpnext_payment_hub.pos.api.get_sales_queue", {
		queue: activeQueue.value,
		...scopeFilterArgs(),
		current_pos_opening_shift: props.posOpeningShift || null,
		search: queueSearch.value || null,
		limit: 100,
	})
	queueRows.value = unwrapPaymentHubResult(result)?.rows || []
}

async function refreshQueues() {
	loading.value = true
	try {
		await Promise.all([loadCounts(), loadQueueRows()])
	} catch (error) {
		showWarning(error?.message || __("Unable to load Payment Hub sales"))
	} finally {
		loading.value = false
	}
}

async function loadHistory() {
	historyLoading.value = true
	try {
		const result = await call("erpnext_payment_hub.pos.reporting.search_transaction_history", {
			search: historySearch.value || null,
			...scopeFilterArgs(),
			limit: 150,
		})
		historyRows.value = unwrapPaymentHubResult(result)?.rows || []
	} catch (error) {
		showWarning(error?.message || __("Unable to load transaction history"))
	} finally {
		historyLoading.value = false
	}
}

async function loadDailyReport() {
	reportLoading.value = true
	try {
		const result = await call("erpnext_payment_hub.pos.reporting.get_daily_transaction_report", {
			...scopeFilterArgs(),
		})
		dailyReport.value = unwrapPaymentHubResult(result) || emptyDailyReport()
	} catch (error) {
		showWarning(error?.message || __("Unable to load daily payment/refund report"))
	} finally {
		reportLoading.value = false
	}
}

function triggerPaymentHubExport(view, fileFormat, args = {}) {
	const params = new URLSearchParams({
		view,
		file_format: fileFormat,
	})
	Object.entries(args).forEach(([key, value]) => {
		if (value !== null && value !== undefined && String(value).trim() !== "") {
			params.set(key, value)
		}
	})

	const link = document.createElement("a")
	link.href = `/api/method/erpnext_payment_hub.pos.reporting.download_transaction_export?${params.toString()}`
	link.target = "_blank"
	link.rel = "noopener"
	document.body.appendChild(link)
	link.click()
	link.remove()
}

function exportHistory(fileFormat) {
	triggerPaymentHubExport("history", fileFormat, {
		search: historySearch.value || null,
		...scopeFilterArgs(),
	})
}

function exportDailyReport(fileFormat) {
	triggerPaymentHubExport("daily", fileFormat, {
		...scopeFilterArgs(),
	})
}

async function checkPayment(row) {
	actionName.value = row.name
	try {
		await call("erpnext_payment_hub.pos.api.check_session_payments", { session_name: row.name })
		await refreshQueues()
		showSuccess(__("Payment status refreshed"))
	} catch (error) {
		showWarning(paymentHubErrorMessage(error, __("Unable to refresh payment status")))
	} finally {
		actionName.value = null
	}
}

async function copyPaymentLink(row) {
	const url = String(row?.payment_url || "").trim()
	if (!url) {
		showWarning(__("Payment link is not available for this transaction"))
		return
	}

	try {
		if (navigator?.clipboard?.writeText) {
			await navigator.clipboard.writeText(url)
		} else {
			const textarea = document.createElement("textarea")
			textarea.value = url
			textarea.setAttribute("readonly", "")
			textarea.style.position = "fixed"
			textarea.style.opacity = "0"
			document.body.appendChild(textarea)
			textarea.select()
			document.execCommand("copy")
			textarea.remove()
		}
		showSuccess(activeQueue.value === "Waiting" && !row.link_expired ? __("Payment link copied") : __("Stored payment link copied"))
	} catch (error) {
		showWarning(__("Unable to copy payment link"))
	}
}

async function resend(row) {
	actionName.value = row.name
	try {
		let allocationName = row.electronic_allocation
		if (!allocationName || row.electronic_status !== "Waiting") {
			const sessionResult = await call("erpnext_payment_hub.pos.api.get_pos_session", { session_name: row.name })
			const session = unwrapPaymentHubResult(sessionResult)
			allocationName = (session?.allocations || []).find((item) => item.channel === "Electronic Payment" && item.status === "Waiting")?.name
		}
		if (!allocationName) throw new Error(__("No waiting electronic payment was found"))
		await call("erpnext_payment_hub.pos.api.resend_payment_link", { allocation_name: allocationName })
		showSuccess(__("Payment link sent again on WhatsApp"))
		await refreshQueues()
	} catch (error) {
		showWarning(paymentHubErrorMessage(error, __("Unable to resend payment link")))
	} finally {
		actionName.value = null
	}
}

async function newPaymentLink(row, sendWhatsapp) {
	actionName.value = row.name
	try {
		const result = unwrapPaymentHubResult(
			await call("erpnext_payment_hub.pos.api.create_new_payment_link", {
				session_name: row.name,
				send_whatsapp: sendWhatsapp ? 1 : 0,
			}),
		)
		const allocation = result?.electronic_allocation
		if (!sendWhatsapp && allocation?.payment_url) {
			try {
				await navigator.clipboard.writeText(allocation.payment_url)
				showSuccess(__("New payment link created and copied"))
			} catch {
				showSuccess(__("New payment link created"))
			}
		} else {
			showSuccess(__("New payment link created and sent on WhatsApp"))
		}
		activeQueue.value = "Waiting"
		await refreshQueues()
	} catch (error) {
		showWarning(paymentHubErrorMessage(error, __("Unable to create a new payment link")))
	} finally {
		actionName.value = null
	}
}

async function printDraft(row) {
	actionName.value = row.name
	const printWindow = window.open("", "_blank")
	try {
		const result = unwrapPaymentHubResult(
			await call("erpnext_payment_hub.pos.api.get_pos_draft_print", {
				session_name: row.name,
				print_type: draftPrintType.value,
			}),
		)
		const url = result?.invoice?.print_url
		if (!url) throw new Error(__("Draft print URL is not available"))
		if (printWindow) {
			printWindow.location.href = url
		} else {
			window.open(url, "_blank")
		}
	} catch (error) {
		if (printWindow) printWindow.close()
		showWarning(paymentHubErrorMessage(error, __("Unable to print this draft")))
	} finally {
		actionName.value = null
	}
}

async function completeAndPrint(row) {
	actionName.value = row.name
	try {
		const callResult = await call("erpnext_payment_hub.pos.api.complete_pos_session", {
			session_name: row.name,
			invoice_doctype: "Sales Invoice",
			submit: 1,
			current_pos_profile: props.posProfile || null,
			current_pos_opening_shift: props.posOpeningShift || null,
		})
		const result = unwrapPaymentHubResult(callResult)
		if (!result?.invoice?.submitted) throw new Error(__("Invoice was created but not submitted"))
		emit("completed", { ...result, payment_hub_session_name: row.name })
		showSuccess(__("Invoice {0} completed", [result.invoice.name]))
		await refreshQueues()
	} catch (error) {
		showWarning(paymentHubErrorMessage(error, __("Unable to complete this sale")))
	} finally {
		actionName.value = null
	}
}

function startQueueAutoRefresh() {
	stopQueueAutoRefresh()
	refreshTimer = window.setInterval(() => {
		if (show.value && activeView.value === "Queues" && !loading.value) refreshQueues()
	}, 10000)
}

function stopQueueAutoRefresh() {
	if (refreshTimer) {
		window.clearInterval(refreshTimer)
		refreshTimer = null
	}
}

watch(show, async (visible) => {
	if (visible) {
		await loadScopeContext(true)
		await refreshActiveView()
		startQueueAutoRefresh()
	} else {
		stopQueueAutoRefresh()
	}
})

watch(activeQueue, () => {
	if (show.value && activeView.value === "Queues") refreshQueues()
})

watch(activeView, (view) => {
	if (!show.value) return
	if (view === "Queues") refreshQueues()
	else if (view === "History") loadHistory()
	else loadDailyReport()
})

watch(
	() => [props.posProfile, props.posOpeningShift],
	async () => {
		selectedProfile.value = props.posProfile || ""
		if (show.value) {
			await loadScopeContext(true)
			await refreshActiveView()
		}
	},
)

onUnmounted(stopQueueAutoRefresh)
</script>
