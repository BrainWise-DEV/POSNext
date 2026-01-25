<template>
	<!-- Full Page Overlay -->
	<Transition name="fade">
		<div
			v-if="show"
			class="fixed inset-0 bg-black bg-opacity-50 z-[300]"
			@click.self="handleClose"
		>
			<!-- Main Container -->
			<div class="fixed inset-0 flex items-center justify-center p-4">
				<div class="w-full h-full max-w-[95vw] max-h-[95vh] bg-white rounded-lg shadow-2xl overflow-hidden flex flex-col">
					<!-- Header -->
					<div class="flex items-center justify-between px-6 py-4 border-b">
						<div class="flex items-center gap-3">
							<FeatherIcon name="tag" class="w-5 h-5 text-gray-700" />
							<div>
								<h2 class="text-lg mb-1 font-semibold text-gray-900">{{ __('Promotion & Coupon Management') }}</h2>
								<p class="text-sm text-gray-600">{{ __('Manage promotional schemes and coupons') }}</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							<Button
								variant="ghost"
								@click="handleClose"
								icon="x"
							>
								<template #icon>
									<FeatherIcon name="x" class="w-4 h-4" />
								</template>
							</Button>
						</div>
					</div>

					<!-- Tabs -->
					<div class="border-b bg-white px-6">
						<div class="flex gap-1">
							<button
								@click="activeTab = 'promotions'"
								:class="[
									'px-4 py-3 text-sm font-medium border-b-2 transition-colors',
									activeTab === 'promotions'
										? 'text-blue-600 border-blue-600'
										: 'text-gray-600 border-transparent hover:text-gray-900 hover:border-gray-300'
								]"
							>
								<div class="flex items-center gap-2">
									<FeatherIcon name="percent" class="w-4 h-4" />
									<span>{{ __('Promotional Schemes') }}</span>
								</div>
							</button>
							<button
								@click="activeTab = 'coupons'"
								:class="[
									'px-4 py-3 text-sm font-medium border-b-2 transition-colors',
									activeTab === 'coupons'
										? 'text-blue-600 border-blue-600'
										: 'text-gray-600 border-transparent hover:text-gray-900 hover:border-gray-300'
								]"
							>
								<div class="flex items-center gap-2">
									<FeatherIcon name="gift" class="w-4 h-4" />
									<span>{{ __('Coupons') }}</span>
								</div>
							</button>
						</div>
					</div>

					<!-- Content: Split Layout -->
					<div class="flex-1 flex overflow-hidden">
						<!-- PROMOTIONS TAB -->
						<template v-if="activeTab === 'promotions'">
						<!-- LEFT SIDE: Promotion List & Navigation -->
						<div class="w-80 flex-shrink-0 border-e bg-gray-50 flex flex-col">
							<!-- Search & Filter -->
							<div class="p-4 bg-white border-b flex flex-col gap-3">
								<FormControl
									type="text"
									v-model="searchQuery"
									:placeholder="__('Search promotions...')"
								>
									<template #prefix>
										<FeatherIcon name="search" class="w-4 h-4 text-gray-500" />
									</template>
								</FormControl>

								<FormControl
									type="select"
									v-model="filterStatus"
									:options="[
										{ label: __('All Status'), value: 'all' },
										{ label: __('Active Only'), value: 'active' },
										{ label: __('Expired Only'), value: 'expired' },
										{ label: __('Not Started'), value: 'not_started' },
										{ label: __('Disabled Only'), value: 'disabled' }
									]"
								/>
							</div>

							<!-- Create New Button -->
							<div class="p-4 bg-white border-b flex flex-col gap-2">
								<Button
									v-if="permissions.create"
									@click="handleCreateNew"
									variant="solid"
									class="w-full"
								>
									<template #prefix>
										<FeatherIcon name="plus-circle" class="w-4 h-4" />
									</template>
									{{ __('Create New Promotion') }}
								</Button>
								<!-- Permission Warning -->
								<div v-else class="px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg">
									<div class="flex items-start gap-2">
										<svg class="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
											<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
										</svg>
										<div class="flex-1">
											<p class="text-xs font-medium text-amber-900">{{ __('Create permission required') }}</p>
										</div>
									</div>
								</div>
								<Button
									@click="loadPromotions"
									variant="outline"
									class="w-full"
									:loading="loading"
								>
									<template #prefix>
										<FeatherIcon name="refresh-cw" class="w-4 h-4" />
									</template>
									{{ __('Refresh') }}
								</Button>
							</div>

							<!-- Promotions List -->
							<div class="flex-1 overflow-y-auto">
								<!-- Loading State -->
								<div v-if="loading && promotions.length === 0" class="flex items-center justify-center py-12">
									<div class="text-center">
										<LoadingIndicator class="w-6 h-6 mx-auto mb-2" />
										<p class="text-sm text-gray-600">{{ __('Loading...') }}</p>
									</div>
								</div>

								<!-- Empty State -->
								<div v-else-if="filteredPromotions.length === 0" class="text-center py-12 px-4">
									<div class="text-gray-400 mb-3">
										<FeatherIcon name="inbox" class="w-12 h-12 mx-auto" />
									</div>
									<p class="text-sm text-gray-600">{{ __('No promotions found') }}</p>
								</div>

								<!-- Promotion Items -->
								<div v-else class="p-2 flex flex-col gap-1">
									<button
										v-for="promotion in filteredPromotions"
										:key="promotion.name"
										@click="handleSelectPromotion(promotion)"
										:class="[
											'w-full text-start p-3 rounded-md transition-all',
											selectedPromotion?.name === promotion.name
												? 'bg-blue-50 ring-2 ring-blue-500 ring-inset'
												: 'hover:bg-gray-100'
										]"
									>
										<div class="flex items-start justify-between mb-2">
											<div class="flex-1 min-w-0">
												<div class="flex items-center gap-2">
													<p :class="[
														'text-sm font-medium truncate',
														selectedPromotion?.name === promotion.name ? 'text-blue-900' : 'text-gray-900'
													]">
														{{ promotion.name }}
													</p>
													<Badge
														v-if="promotion.source === 'Pricing Rule'"
														variant="subtle"
														theme="blue"
														size="sm"
													>
														{{ __('Rule') }}
													</Badge>
													<Badge
														v-else-if="promotion.source === 'Promotional Scheme'"
														variant="subtle"
														theme="purple"
														size="sm"
													>
														{{ __('Scheme') }}
													</Badge>
												</div>
												<p class="text-xs text-gray-500 mt-0.5">{{ __('{0} items', [promotion.items_count || 0]) }}</p>
											</div>
											<Badge
												variant="subtle"
												:theme="getStatusTheme(promotion.status)"
												size="sm"
											>
												{{ promotion.status || __('Active') }}
											</Badge>
										</div>
										<div class="flex items-center justify-between text-xs">
											<Badge variant="subtle">
												{{ translateApplyOn(promotion.apply_on) }}
											</Badge>
											<span class="text-gray-500">
												{{ promotion.valid_upto ? formatDate(promotion.valid_upto) : __('No expiry') }}
											</span>
										</div>
									</button>
								</div>
							</div>
						</div>

						<!-- RIGHT SIDE: Work Area -->
						<div class="flex-1 overflow-y-auto bg-white">
							<!-- Empty State: No Selection -->
							<div v-if="!selectedPromotion && !isCreating" class="flex items-center justify-center h-full">
								<div class="text-center px-8 max-w-md">
									<div class="text-gray-300 mb-4">
										<FeatherIcon name="tag" class="w-16 h-16 mx-auto" />
									</div>
									<h3 class="text-xl font-semibold text-gray-900 mb-2">{{ __('Select a Promotion') }}</h3>
									<p class="text-sm text-gray-600 mb-6">{{ __('Choose a promotion from the list to view and edit, or create a new one to get started') }}</p>
									<Button
										v-if="permissions.create"
										@click="handleCreateNew"
										variant="solid"
									>
										<template #prefix>
											<FeatherIcon name="plus" class="w-4 h-4" />
										</template>
										{{ __('Create New Promotion') }}
									</Button>
									<p v-else class="text-sm text-amber-600">
										{{ __("You don't have permission to create promotions") }}
									</p>
								</div>
							</div>

							<!-- Create/Edit Form -->
							<div v-else class="p-6">
								<div class="max-w-5xl mx-auto">
									<!-- Form Header -->
									<div class="flex items-center justify-between mb-6 pb-4 border-b">
										<div>
											<div class="flex items-center gap-3">
												<h3 class="text-xl font-semibold text-gray-900">
													{{ isCreating ? __('Create New Promotion') : __('Edit Promotion') }}
												</h3>
												<Badge
													v-if="!isCreating && selectedPromotion?.source === 'Pricing Rule'"
													variant="subtle"
													theme="blue"
													size="md"
												>
													{{ __('Pricing Rule') }}
												</Badge>
												<Badge
													v-else-if="!isCreating && selectedPromotion?.source === 'Promotional Scheme'"
													variant="subtle"
													theme="purple"
													size="md"
												>
													{{ __('Promotional Scheme') }}
												</Badge>
											</div>
											<p class="text-sm text-gray-600 mt-1">
												<span v-if="isCreating">
													{{ __('Fill in the details to create a new promotional scheme') }}
												</span>
												<span v-else-if="isPricingRule">
													{{ __('View pricing rule details (read-only)') }}
												</span>
												<span v-else>
													{{ __('Update the promotion details below') }}
												</span>
											</p>
										</div>
										<div class="flex items-center gap-2">
											<!-- Show info badge for read-only Pricing Rules -->
											<div v-if="isPricingRule" class="flex items-center gap-2 px-3 py-1 bg-blue-50 rounded-lg">
												<FeatherIcon name="info" class="w-4 h-4 text-blue-600" />
												<span class="text-xs text-blue-700 font-medium">{{ __('Read-only: Edit in Back Office') }}</span>
											</div>

											<Button
												v-if="!isCreating && !isPricingRule && permissions.delete"
												@click="handleDelete(selectedPromotion)"
												variant="ghost"
												theme="red"
											>
												<template #prefix>
													<FeatherIcon name="trash-2" class="w-4 h-4" />
												</template>
												{{ __('Delete') }}
											</Button>
											<Button
												v-if="!isCreating && !isPricingRule && permissions.write"
												@click="handleToggle(selectedPromotion)"
												variant="outline"
												:theme="selectedPromotion.disable ? 'green' : 'orange'"
											>
												<template #prefix>
													<FeatherIcon :name="selectedPromotion.disable ? 'check-circle' : 'x-circle'" class="w-4 h-4" />
												</template>
												{{ selectedPromotion.disable ? __('Enable') : __('Disable') }}
											</Button>
											<div v-if="!isPricingRule && (permissions.write || permissions.delete)" class="w-px h-6 bg-gray-200"></div>
											<Button
												@click="handleCancel"
												variant="ghost"
											>
												{{ isPricingRule ? __('Close') : __('Cancel') }}
											</Button>
											<Button
												v-if="!isPricingRule && (isCreating ? permissions.create : permissions.write)"
												@click="handleSubmit"
												:loading="loading"
												variant="solid"
											>
												<template #prefix>
													<FeatherIcon :name="isCreating ? 'plus' : 'save'" class="w-4 h-4" />
												</template>
												{{ isCreating ? __('Create') : __('Update') }}
											</Button>
										</div>
									</div>

									<!-- Form Content -->
									<div class="flex flex-col gap-6">
										<!-- Basic Information Card -->
										<Card>
											<div class="p-5">
												<div class="flex items-center gap-2 mb-4">
													<FeatherIcon name="info" class="w-4 h-4 text-blue-600" />
													<h4 class="text-sm font-semibold text-gray-900">{{ __('Basic Information') }}</h4>
												</div>
												<div class="grid grid-cols-3 gap-4">
													<div class="col-span-3">
														<FormControl
															type="text"
															:label="__('Promotion Name')"
															v-model="form.name"
															:disabled="!isCreating"
															:placeholder="__('e.g., Summer Sale 2025')"
															required
														/>
													</div>

													<FormControl
														type="date"
														:label="__('Valid From')"
														v-model="form.valid_from"
														:disabled="isPricingRule"
													/>

													<FormControl
														type="date"
														:label="__('Valid Until')"
														v-model="form.valid_upto"
														:disabled="isPricingRule"
													/>

													<div>
														<label class="block text-sm font-medium text-gray-700 mb-1.5 text-start">
															{{ __('Apply On') }} <span class="text-red-500">*</span>
														</label>
														<SelectInput
															v-model="form.apply_on"
															:disabled="!isCreating || isPricingRule"
															:options="applyOnOptions"
															:placeholder="__('Select option')"
														/>
													</div>
												</div>
											</div>
										</Card>

										<!-- Item Selection Card -->
										<Card v-if="form.apply_on !== 'Transaction'">
											<div class="p-5">
												<div class="flex items-center gap-2 mb-4">
													<FeatherIcon name="list" class="w-4 h-4 text-green-600" />
													<h4 class="text-sm font-semibold text-gray-900">{{ __('Select {0}', [translateApplyOn(form.apply_on)]) }}</h4>
													<Badge variant="subtle" theme="red" size="sm">{{ __('Required') }}</Badge>
												</div>

												<!-- Item Code Selection -->
												<div v-if="form.apply_on === 'Item Code'" class="flex flex-col gap-3">
													<SelectInput
														v-model="selectedItemCode"
														:disabled="!isCreating"
														@change="addItemByCode"
														:options="itemCodeOptions"
														:placeholder="__('Select Item')"
														:searchable="true"
														:searchPlaceholder="__('Search by name or code...')"
														:noResultsText="__('No items found')"
														:maxDisplayed="30"
													/>

													<!-- Selected Items -->
													<div v-if="form.items.length > 0" class="flex flex-wrap gap-2 items-center">
														<Badge
															v-for="(item, index) in form.items"
															:key="index"
															variant="subtle"
															theme="blue"
														>
															{{ item.item_name || item.item_code }}
															<button
																@click="removeItem(index)"
																class="ms-1 hover:text-blue-900"
															>
																×
															</button>
														</Badge>
														<button
															v-if="form.items.length > 1 && isCreating"
															@click="clearAllItems"
															class="text-xs text-red-600 hover:text-red-800 hover:underline"
														>
															{{ __('Clear All') }}
														</button>
													</div>
												</div>

												<!-- Item Group Selection -->
												<div v-else-if="form.apply_on === 'Item Group'" class="flex flex-col gap-3">
													<SelectInput
														v-model="selectedItemGroup"
														:disabled="!isCreating"
														@change="addItemGroup"
														:options="itemGroupOptions"
														:placeholder="__('Select Item Group')"
													/>

													<div v-if="form.items.length > 0" class="flex flex-wrap gap-2 items-center">
														<Badge
															v-for="(item, index) in form.items"
															:key="index"
															variant="subtle"
															theme="green"
														>
															{{ item.item_group }}
															<button
																@click="removeItem(index)"
																class="ms-1 hover:text-green-900"
															>
																×
															</button>
														</Badge>
														<button
															v-if="form.items.length > 1 && isCreating"
															@click="clearAllItems"
															class="text-xs text-red-600 hover:text-red-800 hover:underline"
														>
															{{ __('Clear All') }}
														</button>
													</div>
												</div>

												<!-- Brand Selection -->
												<div v-else-if="form.apply_on === 'Brand'" class="flex flex-col gap-3">
													<SelectInput
														v-model="selectedBrand"
														:disabled="!isCreating"
														@change="addBrand"
														:options="brandOptions"
														:placeholder="__('Select Brand')"
													/>

													<div v-if="form.items.length > 0" class="flex flex-wrap gap-2 items-center">
														<Badge
															v-for="(item, index) in form.items"
															:key="index"
															variant="subtle"
															theme="purple"
														>
															{{ item.brand }}
															<button
																@click="removeItem(index)"
																class="ms-1 hover:text-purple-900"
															>
																×
															</button>
														</Badge>
														<button
															v-if="form.items.length > 1 && isCreating"
															@click="clearAllItems"
															class="text-xs text-red-600 hover:text-red-800 hover:underline"
														>
															{{ __('Clear All') }}
														</button>
													</div>
												</div>
											</div>
										</Card>

										<!-- Discount Details Card -->
										<Card>
											<div class="p-5">
												<div class="flex items-center gap-2 mb-4">
													<FeatherIcon name="percent" class="w-4 h-4 text-purple-600" />
													<h4 class="text-sm font-semibold text-gray-900">{{ __('Discount Details') }}</h4>
													<Badge variant="subtle" theme="red" size="sm">{{ __('Required') }}</Badge>
												</div>

												<div class="flex flex-col gap-4">
													<!-- Discount Type Selection -->
													<div>
														<label class="block text-sm font-medium text-gray-700 mb-3 text-start">{{ __('Discount Type') }}</label>
														<div class="grid grid-cols-3 gap-3">
															<button
																v-for="type in discountTypes"
																:key="type.value"
																@click="form.discount_type = type.value"
																:disabled="!isCreating"
																:class="[
																	'p-3 border rounded-lg transition-all flex items-center justify-center gap-2',
																	form.discount_type === type.value
																		? 'border-blue-600 bg-blue-50 text-blue-900'
																		: 'border-gray-300 hover:border-gray-400 text-gray-700',
																	!isCreating ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
																]"
															>
																<FeatherIcon :name="type.icon" class="w-4 h-4" />
																<span class="text-sm font-medium">{{ type.label }}</span>
															</button>
														</div>
													</div>

													<!-- Discount Values -->
													<div class="grid grid-cols-3 gap-4">
														<FormControl
															v-if="form.discount_type !== 'free_item'"
															type="number"
															:label="form.discount_type === 'percentage' ? __('Discount (%)') : __('discount ({0})', [currency])"
															v-model="form.discount_value"
															placeholder="0"
															:disabled="isPricingRule"
															required
														/>

														<!-- Free Item Search -->
														<div v-if="form.discount_type === 'free_item'" class="flex flex-col gap-2">
															<label class="block text-sm font-medium text-gray-700 text-start">{{ __('Free Item') }}<span class="text-red-500"> *</span></label>

															<!-- Search Input -->
															<FormControl
																v-if="!form.free_item"
																type="text"
																v-model="freeItemSearch"
																:placeholder="__('Search item... (min 2 characters)')"
															>
																<template #prefix>
																	<FeatherIcon name="search" class="w-4 h-4 text-gray-500" />
																</template>
															</FormControl>

															<!-- Search Results -->
															<div v-if="freeItemSearchResults.length > 0 && !form.free_item" class="border rounded-lg overflow-hidden">
																<div class="max-h-40 overflow-y-auto divide-y">
																	<button
																		v-for="item in freeItemSearchResults"
																		:key="item.item_code"
																		@click="selectFreeItem(item)"
																		type="button"
																		class="w-full text-start px-4 py-2 hover:bg-gray-50 transition-colors"
																	>
																		<p class="text-sm font-medium text-gray-900">{{ item.item_name }}</p>
																		<p class="text-xs text-gray-500">{{ item.item_code }}</p>
																	</button>
																</div>
															</div>

															<!-- Selected Free Item -->
															<div v-if="form.free_item" class="flex items-center gap-2">
																<Badge variant="subtle" theme="green" size="md">
																	{{ form.free_item }}
																	<button
																		@click="form.free_item = ''"
																		type="button"
																		class="ms-2 hover:text-green-900"
																	>
																		×
																	</button>
																</Badge>
															</div>
														</div>

														<FormControl
															v-if="form.discount_type === 'free_item'"
															type="number"
															:label="__('Free Quantity')"
															v-model="form.free_qty"
															placeholder="1"
															:disabled="isPricingRule"
															required
														/>

														<FormControl
															type="number"
															:label="__('Minimum Quantity')"
															v-model="form.min_qty"
															placeholder="0"
															:disabled="isPricingRule"
														/>

														<FormControl
															type="number"
															:label="__('Maximum Quantity')"
															v-model="form.max_qty"
															placeholder="0"
															:disabled="isPricingRule"
														/>

														<FormControl
															type="number"
															:label="__('Minimum Amount ({0})', [currency])"
															v-model="form.min_amt"
															placeholder="0"
															:disabled="isPricingRule"
														/>

														<FormControl
															type="number"
															:label="__('Maximum Amount ({0})', [currency])"
															v-model="form.max_amt"
															placeholder="0"
															:disabled="isPricingRule"
														/>
													</div>
												</div>
											</div>
										</Card>
									</div>
								</div>
							</div>
						</div>
						</template>

						<!-- COUPONS TAB -->
						<CouponManagement
							v-if="activeTab === 'coupons'"
							:company="company"
							:currency="currency"
							:permissions="permissions"
							@coupon-saved="handleCouponSaved"
						/>
					</div>
				</div>

				<!-- Delete Confirmation Dialog -->
				<Transition name="fade">
					<div
						v-if="showDeleteConfirm"
						class="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[400]"
						@click.self="cancelDelete"
					>
						<div class="bg-white rounded-lg shadow-2xl max-w-md w-full mx-4 p-6">
							<div class="flex items-start gap-4">
								<div class="flex-shrink-0">
									<div class="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center">
										<FeatherIcon name="alert-triangle" class="w-6 h-6 text-red-600" />
									</div>
								</div>
								<div class="flex-1">
									<h3 class="text-lg font-semibold text-gray-900 mb-2">{{ __('Delete Promotion') }}</h3>
									<TranslatedHTML
										:tag="'p'"
										class="text-sm text-gray-600 mb-1"
										:inner="__('Are you sure you want to delete &lt;strong&gt;&quot;{0}&quot;&lt;strong&gt;?', [promotionToDelete?.name])"
									/>
									<p class="text-sm text-gray-500">
										{{ __('This will also delete all associated pricing rules. This action cannot be undone.') }}
									</p>
								</div>
							</div>
							<div class="flex justify-end gap-3 mt-6">
								<Button
									@click="cancelDelete"
									variant="ghost"
								>
									{{ __('Cancel') }}
								</Button>
								<Button
									@click="confirmDelete"
									variant="solid"
									theme="red"
								>
									<template #prefix>
										<FeatherIcon name="trash-2" class="w-4 h-4" />
									</template>
									{{ __('Delete Promotion') }}
								</Button>
							</div>
						</div>
					</div>
				</Transition>
			</div>
		</div>
	</Transition>
</template>

<script setup>
import { usePOSPermissions } from "@/composables/usePermissions"
import { useToast } from "@/composables/useToast"
import { useItemSearchStore } from "@/stores/itemSearch"
import { __ } from "@/utils/translation"
import CouponManagement from "./CouponManagement.vue"
import SelectInput from "../common/SelectInput.vue"
import {
	Badge,
	Button,
	Card,
	FormControl,
	LoadingIndicator,
	createResource,
} from "frappe-ui"
import { FeatherIcon } from "frappe-ui"
import { computed, onMounted, ref, watch } from "vue"
import TranslatedHTML from "../common/TranslatedHTML.vue"

// Use shared toast
const { showSuccess, showError, showWarning } = useToast()

// Permission checks
const { canCreatePromotion, canEditPromotion, canDeletePromotion } =
	usePOSPermissions()
const permissions = ref({
	create: true,
	write: true,
	delete: true,
})

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	company: String,
	currency: {
		type: String,
		default: "USD",
	},
})

const emit = defineEmits(["update:modelValue", "promotion-saved"])

// Access cached items from the store
const itemSearchStore = useItemSearchStore()

const show = ref(props.modelValue)
const loading = ref(false)
const isCreating = ref(false)
const selectedPromotion = ref(null)
const showDeleteConfirm = ref(false)
const promotionToDelete = ref(null)
const activeTab = ref("promotions") // Tab state: 'promotions' or 'coupons'

// List view state
const promotions = ref([])
const searchQuery = ref("")
const filterStatus = ref("all")

// Form state
const form = ref({
	name: "",
	company: props.company,
	apply_on: "Item Group",
	discount_type: "percentage",
	discount_value: 0,
	free_item: "",
	free_qty: 1,
	items: [],
	min_qty: 0,
	max_qty: 0,
	min_amt: 0,
	max_amt: 0,
	valid_from: "",
	valid_upto: "",
})

// Dropdown data
const itemGroups = ref([])
const brands = ref([])
const itemSearch = ref("")
const freeItemSearch = ref("")
const selectedItemGroup = ref("")
const selectedBrand = ref("")

// Discount types
const discountTypes = [
	{ value: "percentage", label: __("Percentage"), icon: "percent" },
	{ value: "amount", label: __("Fixed Amount"), icon: "dollar-sign" },
	{ value: "free_item", label: __("Free Item"), icon: "gift" },
]

// Computed
const isPricingRule = computed(() => {
	return !isCreating.value && selectedPromotion.value?.source === "Pricing Rule"
})

const filteredPromotions = computed(() => {
	let filtered = promotions.value

	// Filter by search query
	if (searchQuery.value) {
		filtered = filtered.filter((p) =>
			p.name.toLowerCase().includes(searchQuery.value.toLowerCase()),
		)
	}

	// Filter by status
	if (filterStatus.value === "active") {
		filtered = filtered.filter((p) => p.status === "Active")
	} else if (filterStatus.value === "expired") {
		filtered = filtered.filter((p) => p.status === "Expired")
	} else if (filterStatus.value === "not_started") {
		filtered = filtered.filter((p) => p.status === "Not Started")
	} else if (filterStatus.value === "disabled") {
		filtered = filtered.filter((p) => p.status === "Disabled")
	}

	return filtered
})

// Computed: Filter cached items based on search term
const searchResults = computed(() => {
	if (!itemSearch.value || itemSearch.value.length < 2) {
		return []
	}

	const term = itemSearch.value.toLowerCase()
	const allItems = itemSearchStore.allItems || []

	// Filter items by search term
	const filtered = allItems.filter(
		(item) =>
			item.item_code?.toLowerCase().includes(term) ||
			item.item_name?.toLowerCase().includes(term) ||
			item.barcode?.toLowerCase().includes(term),
	)

	// Limit to 20 results for performance
	return filtered.slice(0, 20)
})

// Computed: Filter cached items for free item selection
const freeItemSearchResults = computed(() => {
	if (!freeItemSearch.value || freeItemSearch.value.length < 2) {
		return []
	}

	const term = freeItemSearch.value.toLowerCase()
	const allItems = itemSearchStore.allItems || []

	// Filter items by search term
	const filtered = allItems.filter(
		(item) =>
			item.item_code?.toLowerCase().includes(term) ||
			item.item_name?.toLowerCase().includes(term) ||
			item.barcode?.toLowerCase().includes(term),
	)

	// Limit to 20 results for performance
	return filtered.slice(0, 20)
})

// Single source of truth for apply_on configuration
// Used by both applyOnOptions dropdown and translateApplyOn function
const APPLY_ON_CONFIG = {
	'Item Code': { label: () => __('Specific Items') },
	'Item Group': { label: () => __('Item Groups') },
	'Brand': { label: () => __('Brands') },
	'Transaction': { label: () => __('Entire Transaction') }
}

// Computed: Options for Apply On dropdown
const applyOnOptions = computed(() =>
	Object.entries(APPLY_ON_CONFIG).map(([value, config]) => ({
		label: config.label(),
		value
	}))
)

// Computed: Options for Item Group dropdown
const itemGroupOptions = computed(() =>
	itemGroups.value.map(g => ({ label: g.name, value: g.name }))
)

// Computed: Options for Brand dropdown
const brandOptions = computed(() =>
	brands.value.map(b => ({ label: b.name, value: b.name }))
)

// Item Code selection
const selectedItemCode = ref("")

// Computed: Options for Item Code dropdown (searchable)
const itemCodeOptions = computed(() => {
	const allItems = itemSearchStore.allItems || []
	return allItems.map(item => ({
		label: item.item_name,
		value: item.item_code,
		subtitle: item.item_code
	}))
})

// Resources
const promotionsResource = createResource({
	url: "pos_next.api.promotions.get_promotions",
	makeParams() {
		return {
			pos_profile: props.posProfile,
			company: props.company,
			include_disabled: true,
		}
	},
	auto: false,
	onSuccess(data) {
		promotions.value = data || []
		loading.value = false
	},
})

const itemGroupsResource = createResource({
	url: "pos_next.api.promotions.get_item_groups",
	makeParams() {
		return { company: props.company }
	},
	auto: false,
	onSuccess(data) {
		itemGroups.value = data || []
	},
	onError(error) {
		console.error("Error loading item groups:", error)
		handleError(error, __("Failed to load item groups"))
	},
})

const brandsResource = createResource({
	url: "pos_next.api.promotions.get_brands",
	auto: false,
	onSuccess(data) {
		brands.value = data || []
	},
	onError(error) {
		console.error("Error loading brands:", error)
		handleError(error, __("Failed to load brands"))
	},
})

const savePromotionResource = createResource({
	url: "pos_next.api.promotions.create_promotion",
	makeParams() {
		return { data: JSON.stringify(form.value) }
	},
	auto: false,
	onSuccess(data) {
		loading.value = false
		const responseData = data?.message || data
		const successMessage =
			responseData?.message || __("Promotion created successfully")

		showSuccess(successMessage)
		emit("promotion-saved", responseData)
		loadPromotions()
		returnToList()
	},
	onError(error) {
		loading.value = false
		handleError(error, __('Failed to create promotion'))
	},
})

const updatePromotionResource = createResource({
	url: "pos_next.api.promotions.update_promotion",
	makeParams() {
		return {
			scheme_name: form.value.name,
			data: JSON.stringify({
				valid_from: form.value.valid_from,
				valid_upto: form.value.valid_upto,
				min_qty: form.value.min_qty,
				max_qty: form.value.max_qty,
				min_amt: form.value.min_amt,
				max_amt: form.value.max_amt,
				discount_value: form.value.discount_value,
				free_item: form.value.free_item,
				free_qty: form.value.free_qty,
			}),
		}
	},
	auto: false,
	onSuccess(data) {
		loading.value = false
		const responseData = data?.message || data
		const successMessage =
			responseData?.message || __("Promotion updated successfully")

		showSuccess(successMessage)
		loadPromotions()
		returnToList()
	},
	onError(error) {
		loading.value = false
		handleError(error, __("Failed to update promotion"))
	},
})

const toggleResource = createResource({
	url: "pos_next.api.promotions.toggle_promotion",
	auto: false,
	onSuccess() {
		showSuccess(__("Promotion status updated successfully"))
		loadPromotions()
	},
	onError(error) {
		handleError(error, __("Failed to update promotion status"))
	},
})

const deleteResource = createResource({
	url: "pos_next.api.promotions.delete_promotion",
	auto: false,
	onSuccess(data) {
		const responseData = data?.message || data
		const successMessage =
			responseData?.message || __("Promotion deleted successfully")

		showSuccess(successMessage)

		// Close delete confirmation dialog
		showDeleteConfirm.value = false
		promotionToDelete.value = null

		// Reload and return to list
		loadPromotions()
		returnToList()
	},
	onError(error) {
		loading.value = false
		showDeleteConfirm.value = false
		promotionToDelete.value = null
		handleError(error, __("Failed to delete promotion"))
	},
})

const promotionDetailsResource = createResource({
	url: "pos_next.api.promotions.get_promotion_details",
	makeParams() {
		return {
			scheme_name: selectedPromotion.value?.name,
		}
	},
	auto: false,
	onSuccess(data) {
		loading.value = false
		populateFormFromPromotion(data)
	},
	onError(error) {
		loading.value = false
		handleError(error, __("Failed to load promotion details"))
	},
})

watch(
	() => props.modelValue,
	(val) => {
		show.value = val
		if (val) {
			loadPromotions()
			loadData()
			checkPermissions()
		}
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
	if (!val) {
		resetForm()
		selectedPromotion.value = null
		isCreating.value = false
	}
})

// Clear items when apply_on type changes (only when creating new promotion)
watch(
	() => form.value.apply_on,
	(newVal, oldVal) => {
		if (isCreating.value && oldVal && newVal !== oldVal) {
			form.value.items = []
		}
	}
)

onMounted(() => {
	checkPermissions()
})

// Check user permissions
async function checkPermissions() {
	try {
		const [create, write, del] = await Promise.all([
			canCreatePromotion(),
			canEditPromotion(),
			canDeletePromotion(),
		])
		permissions.value = {
			create,
			write,
			delete: del,
		}
	} catch (error) {
		console.error("Error checking promotion permissions:", error)
		permissions.value = {
			create: false,
			write: false,
			delete: false,
		}
	}
}

// Utility: Parse error messages from server response
function parseErrorMessage(error) {
	try {
		// Check if there's a _server_messages field
		if (error._server_messages) {
			const messages = JSON.parse(error._server_messages)
			if (Array.isArray(messages) && messages.length > 0) {
				const firstMessage =
					typeof messages[0] === "string"
						? JSON.parse(messages[0])
						: messages[0]
				return firstMessage.message || error.message || __("An error occurred")
			}
		}
		// Fallback to error.message
		return error.message || __("An error occurred")
	} catch (e) {
		return error.message || __("An error occurred")
	}
}

// Utility: Show error with proper parsing
function handleError(error, defaultMessage = __("An error occurred")) {
	const errorMessage = parseErrorMessage(error)
	showError(errorMessage || defaultMessage)
}

// Utility: Reset form and return to list view (keep dialog open)
function returnToList() {
	resetForm()
	selectedPromotion.value = null
	isCreating.value = false
}

function loadPromotions() {
	loading.value = true
	promotionsResource.reload()
}

function loadData() {
	itemGroupsResource.reload()
	brandsResource.reload()
}

function handleClose() {
	show.value = false
}

function handleCreateNew() {
	resetForm()
	isCreating.value = true
	selectedPromotion.value = null
}

function handleSelectPromotion(promotion) {
	isCreating.value = false
	selectedPromotion.value = promotion
	loading.value = true
	promotionDetailsResource.reload()
}

function handleCancel() {
	resetForm()
	selectedPromotion.value = null
	isCreating.value = false
}

function handleToggle(promotion) {
	toggleResource.submit({ scheme_name: promotion.name })
}

function handleDelete(promotion) {
	promotionToDelete.value = promotion
	showDeleteConfirm.value = true
}

function confirmDelete() {
	if (promotionToDelete.value) {
		loading.value = true
		deleteResource.submit({ scheme_name: promotionToDelete.value.name })
	}
}

function cancelDelete() {
	showDeleteConfirm.value = false
	promotionToDelete.value = null
}

function handleSubmit() {
	// Validate
	if (!form.value.name) {
		showWarning(__("Please enter a promotion name"))
		return
	}

	// Check for duplicate name when creating
	if (isCreating.value) {
		const duplicate = promotions.value.find(
			(p) => p.name.toLowerCase() === form.value.name.toLowerCase(),
		)
		if (duplicate) {
			showWarning(
				__('Promotion "{0}" already exists. Please use a different name.', [form.value.name])
			)
			return
		}
	}

	if (form.value.apply_on !== "Transaction" && form.value.items.length === 0) {
		showWarning(__('Please select at least one {0}', [translateApplyOn(form.value.apply_on)]))
		return
	}

	loading.value = true

	if (isCreating.value) {
		savePromotionResource.reload()
	} else {
		updatePromotionResource.reload()
	}
}

function addItem(item) {
	if (!form.value.items.some((i) => i.item_code === item.item_code)) {
		form.value.items.push({ item_code: item.item_code })
	}
	// Clear search term (searchResults will automatically update via computed)
	itemSearch.value = ""
}

function addItemByCode() {
	if (
		selectedItemCode.value &&
		!form.value.items.some((i) => i.item_code === selectedItemCode.value)
	) {
		// Find the item name from allItems
		const allItems = itemSearchStore.allItems || []
		const selectedItem = allItems.find(item => item.item_code === selectedItemCode.value)
		const itemName = selectedItem?.item_name || selectedItemCode.value
		form.value.items.push({ item_code: selectedItemCode.value, item_name: itemName })
	}
	selectedItemCode.value = ""
}

function addItemGroup() {
	if (
		selectedItemGroup.value &&
		!form.value.items.some((i) => i.item_group === selectedItemGroup.value)
	) {
		form.value.items.push({ item_group: selectedItemGroup.value })
	}
	selectedItemGroup.value = ""
}

function addBrand() {
	if (
		selectedBrand.value &&
		!form.value.items.some((i) => i.brand === selectedBrand.value)
	) {
		form.value.items.push({ brand: selectedBrand.value })
	}
	selectedBrand.value = ""
}

function removeItem(index) {
	form.value.items.splice(index, 1)
}

function clearAllItems() {
	form.value.items = []
}

function selectFreeItem(item) {
	form.value.free_item = item.item_code
	freeItemSearch.value = ""
}

function resetForm() {
	form.value = {
		name: "",
		company: props.company,
		apply_on: "Item Group",
		discount_type: "percentage",
		discount_value: 0,
		free_item: "",
		free_qty: 1,
		items: [],
		min_qty: 0,
		max_qty: 0,
		min_amt: 0,
		max_amt: 0,
		valid_from: "",
		valid_upto: "",
	}
	itemSearch.value = ""
	freeItemSearch.value = ""
	selectedItemGroup.value = ""
	selectedBrand.value = ""
}

function populateFormFromPromotion(promotion) {
	// Reset form first
	resetForm()

	// Basic fields
	form.value.name = promotion.name
	form.value.company = promotion.company
	form.value.apply_on = promotion.apply_on
	form.value.valid_from = promotion.valid_from || ""
	form.value.valid_upto = promotion.valid_upto || ""

	// Populate items/item_groups/brands based on apply_on
	if (promotion.apply_on === "Item Code" && promotion.items) {
		form.value.items = promotion.items.map((item) => ({
			item_code: item.item_code,
			uom: item.uom,
		}))
	} else if (promotion.apply_on === "Item Group" && promotion.item_groups) {
		form.value.items = promotion.item_groups.map((group) => ({
			item_group: group.item_group,
			uom: group.uom,
		}))
	} else if (promotion.apply_on === "Brand" && promotion.brands) {
		form.value.items = promotion.brands.map((brand) => ({
			brand: brand.brand,
			uom: brand.uom,
		}))
	}

	// Populate discount details from slabs
	if (
		promotion.price_discount_slabs &&
		promotion.price_discount_slabs.length > 0
	) {
		const slab = promotion.price_discount_slabs[0]
		form.value.min_qty = slab.min_qty || 0
		form.value.max_qty = slab.max_qty || 0
		form.value.min_amt = slab.min_amount || 0
		form.value.max_amt = slab.max_amount || 0

		if (slab.rate_or_discount === "Discount Percentage") {
			form.value.discount_type = "percentage"
			form.value.discount_value = slab.discount_percentage || 0
		} else if (slab.rate_or_discount === "Discount Amount") {
			form.value.discount_type = "amount"
			form.value.discount_value = slab.discount_amount || 0
		}
	} else if (
		promotion.product_discount_slabs &&
		promotion.product_discount_slabs.length > 0
	) {
		const slab = promotion.product_discount_slabs[0]
		form.value.discount_type = "free_item"
		form.value.free_item = slab.free_item || ""
		form.value.free_qty = slab.free_qty || 1
		form.value.min_qty = slab.min_qty || 0
		form.value.max_qty = slab.max_qty || 0
		form.value.min_amt = slab.min_amount || 0
		form.value.max_amt = slab.max_amount || 0
	}
}

function formatDate(dateStr) {
	if (!dateStr) return ""
	const date = new Date(dateStr)
	return date.toLocaleDateString("en-US", {
		month: "short",
		day: "numeric",
		year: "numeric",
	})
}

function getStatusTheme(status) {
	switch (status) {
		case "Active":
			return "green"
		case "Expired":
			return "red"
		case "Not Started":
			return "orange"
		case "Disabled":
			return "gray"
		default:
			return "gray"
	}
}

// Translate apply_on values for display (uses APPLY_ON_CONFIG for consistency)
function translateApplyOn(value) {
	return APPLY_ON_CONFIG[value]?.label() || value
}

function handleCouponSaved(data) {
	// Emit event to parent if needed
	emit("promotion-saved", data)
}
</script>

<style scoped>
/* Fade transition for overlay */
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}
</style>
