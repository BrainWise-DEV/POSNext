<template>
	<!-- Full Page Overlay -->
	<Transition name="fade">
		<div
			v-if="show"
			class="fixed inset-0 bg-black bg-opacity-50 z-[300]"
			@click.self="handleClose"
		>
			<!-- Main Container -->
			<div class="fixed inset-0 flex items-center justify-center sm:p-4">
				<div
					class="w-full h-full bg-white shadow-2xl overflow-hidden flex flex-col sm:max-w-[95vw] sm:max-h-[95vh] sm:rounded-lg"
				>
					<!-- Header -->
					<div
						class="flex items-center justify-between gap-3 border-b px-4 py-3 sm:px-6 sm:py-4"
					>
						<div class="flex items-center gap-3">
							<FeatherIcon name="box" class="w-5 h-5 text-gray-700" />
							<div>
								<h2 class="text-lg mb-1 font-semibold text-gray-900">
									{{ __("Product Management") }}
								</h2>
								<p class="text-sm text-gray-600">
									{{ __("Manage products for POS") }}
								</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							<Button variant="ghost" @click="handleClose" icon="x">
								<template #icon>
									<FeatherIcon name="x" class="w-4 h-4" />
								</template>
							</Button>
						</div>
					</div>

					<!-- Content: Split Layout -->
					<div class="flex-1 flex overflow-hidden">
						<!-- LEFT SIDE: Product List & Navigation -->
						<!--
							Below md the list and the form show one at a time (master-detail);
							320px of list plus a form does not fit on a phone.
						-->
						<div
							:class="[
								'w-full md:w-80 flex-shrink-0 border-e bg-gray-50 flex-col',
								isFormOpen ? 'hidden md:flex' : 'flex',
							]"
						>
							<!-- Search & Filter -->
							<div class="p-4 bg-white border-b flex flex-col gap-3">
								<FormControl
									type="text"
									v-model="searchQuery"
									:placeholder="__('Search products...')"
									@keydown.enter="refreshProducts"
								>
									<template #prefix>
										<FeatherIcon name="search" class="w-4 h-4 text-gray-500" />
									</template>
								</FormControl>

								<SelectInput
									v-model="filterGroup"
									:options="itemGroupOptions"
									:placeholder="__('All Groups')"
									:searchable="true"
									:search-placeholder="__('Search item groups...')"
								/>
							</div>

							<!-- Create New Button -->
							<div class="p-4 bg-white border-b flex flex-col gap-2">
								<Button @click="handleCreateNew" variant="solid" class="w-full">
									<template #prefix>
										<FeatherIcon name="plus-circle" class="w-4 h-4" />
									</template>
									{{ __("Add Product") }}
								</Button>
								<Button
									@click="refreshProducts"
									variant="outline"
									class="w-full"
									:loading="loading"
								>
									<template #prefix>
										<FeatherIcon name="refresh-cw" class="w-4 h-4" />
									</template>
									{{ __("Refresh") }}
								</Button>
							</div>

							<!-- Products List -->
							<div class="flex-1 overflow-y-auto">
								<div
									v-if="loading && products.length === 0"
									class="flex items-center justify-center py-12"
								>
									<div class="text-center">
										<LoadingIndicator class="w-6 h-6 mx-auto mb-2" />
										<p class="text-sm text-gray-600">{{ __("Loading...") }}</p>
									</div>
								</div>

								<div
									v-else-if="products.length === 0"
									class="text-center py-12 px-4"
								>
									<div class="text-gray-400 mb-3">
										<FeatherIcon name="inbox" class="w-12 h-12 mx-auto" />
									</div>
									<p class="text-sm font-medium text-gray-900">
										{{
											hasActiveProductFilters
												? __("No matching products found")
												: __("No products found")
										}}
									</p>
									<p
										v-if="hasActiveProductFilters"
										class="mt-1 text-xs text-gray-500"
									>
										{{ __("Adjust the search or item group filter.") }}
									</p>
								</div>

								<div v-else class="divide-y">
									<button
										v-for="product in products"
										:key="product.name"
										@click="selectProduct(product)"
										:class="[
											'w-full text-start p-4 hover:bg-white transition-colors relative flex items-center gap-3',
											selectedProduct?.name === product.name
												? 'bg-white border-s-4 border-blue-600'
												: 'border-s-4 border-transparent',
										]"
									>
										<div
											class="w-10 h-10 flex-shrink-0 bg-gray-100 rounded overflow-hidden"
										>
											<img
												v-if="product.image"
												:src="product.image"
												class="w-full h-full object-cover"
											/>
											<FeatherIcon
												v-else
												name="image"
												class="w-5 h-5 m-2.5 text-gray-400"
											/>
										</div>
										<div class="flex-1 min-w-0">
											<div class="flex items-center justify-between mb-1">
												<h3
													class="text-sm font-medium text-gray-900 truncate pe-2"
												>
													{{ product.item_name }}
												</h3>
												<Badge
													v-if="product.disabled"
													theme="gray"
													size="sm"
													>{{ __("Disabled") }}</Badge
												>
											</div>
											<div
												class="flex items-center gap-2 text-xs text-gray-500"
											>
												<span class="truncate">{{
													product.item_group
												}}</span>
												<span>•</span>
												<span>{{ formatCurrency(product.price) }}</span>
											</div>
										</div>
									</button>
								</div>

								<div v-if="products.length > 0" class="p-3 bg-white border-t">
									<Button
										v-if="hasMore"
										@click="loadMoreProducts"
										variant="outline"
										class="w-full"
										:loading="loadingMore"
									>
										{{ __("Load more") }}
									</Button>
									<p v-else class="text-xs text-center text-gray-500">
										{{ __("Showing all products") }}
									</p>
								</div>
							</div>
						</div>

						<!-- RIGHT SIDE: Details / Edit Form -->
						<div
							:class="[
								'flex-1 flex-col bg-white overflow-hidden relative',
								isFormOpen ? 'flex' : 'hidden md:flex',
							]"
						>
							<!-- Empty State -->
							<div
								v-if="!selectedProduct && !isCreating"
								class="absolute inset-0 flex items-center justify-center bg-gray-50/50"
							>
								<div class="text-center">
									<div
										class="w-16 h-16 bg-blue-50 text-blue-500 rounded-full flex items-center justify-center mx-auto mb-4"
									>
										<FeatherIcon name="box" class="w-8 h-8" />
									</div>
									<h3 class="text-lg font-medium text-gray-900 mb-2">
										{{ __("Select a Product") }}
									</h3>
									<p class="text-sm text-gray-500 max-w-sm">
										{{
											__(
												"Choose a product from the list to view or edit its details, or create a new one."
											)
										}}
									</p>
								</div>
							</div>

							<!-- Form View -->
							<template v-else>
								<!-- Top Action Bar -->
								<div
									class="flex flex-wrap items-center justify-between gap-3 border-b bg-white px-4 py-3 sm:px-6 sm:py-4 z-10"
								>
									<div class="flex min-w-0 items-center gap-2">
										<!-- The list is hidden behind the form below md, so
										     mobile needs an explicit way back to it. -->
										<button
											type="button"
											@click="returnToList"
											class="-ms-1 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-800 md:hidden"
											:aria-label="__('Back to products')"
										>
											<FeatherIcon
												name="arrow-left"
												class="h-5 w-5 rtl:rotate-180"
											/>
										</button>
										<h3
											class="truncate text-base font-semibold text-gray-900 sm:text-lg"
										>
											{{
												isCreating
													? __("New Product")
													: selectedProduct.item_name
											}}
										</h3>
									</div>
									<div class="flex items-center gap-2">
										<Button
											v-if="form.item_code"
											@click="viewOnDesk"
											variant="outline"
										>
											<template #prefix>
												<FeatherIcon
													name="external-link"
													class="w-4 h-4"
												/>
											</template>
											{{ __("View on Desk") }}
										</Button>
										<Button @click="returnToList" variant="subtle">
											{{ __("Cancel") }}
										</Button>
										<Button
											@click="saveProduct"
											variant="solid"
											theme="blue"
											:loading="saveLoading"
										>
											{{ __("Save") }}
										</Button>
									</div>
								</div>

								<!-- Form Content -->
								<div class="flex-1 overflow-y-auto">
									<div class="mx-auto w-full max-w-[1400px] p-4 sm:p-6">
										<!--
											Two-column workspace. Below lg it collapses to one column with
											the image on top; the grid handles RTL on its own, so the image
											sits on the end side in both directions.
										-->
										<div
											class="grid items-start gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(300px,380px)] min-[1536px]:grid-cols-[minmax(0,1fr)_minmax(340px,460px)]"
										>
											<!-- ============ IMAGE PANEL ============ -->
											<aside
												class="order-first w-full max-w-[320px] xl:order-none xl:max-w-none xl:sticky xl:top-0"
											>
												<input
													type="file"
													:accept="imageAccept"
													@change="handleImageSelect"
													ref="fileInput"
													class="hidden"
												/>

												<!-- The image is the click target and the drop zone -->
												<button
													type="button"
													@click="fileInput?.click()"
													@dragenter.prevent="isDraggingImage = true"
													@dragover.prevent="isDraggingImage = true"
													@dragleave.prevent="isDraggingImage = false"
													@drop.prevent="handleImageDrop"
													:class="[
														'group relative block w-full aspect-square overflow-hidden rounded-xl border-2 transition-colors',
														isDraggingImage
															? 'border-blue-500 border-solid bg-blue-50'
															: form.image
															? 'border-solid border-gray-200 bg-gray-50'
															: 'border-dashed border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50/40',
													]"
													:aria-label="
														form.image
															? __('Change product image')
															: __('Upload product image')
													"
												>
													<img
														v-if="form.image"
														:src="form.image"
														alt=""
														class="h-full w-full object-contain"
													/>
													<div
														v-else
														class="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center"
													>
														<div
															class="flex h-16 w-16 items-center justify-center rounded-full bg-white text-gray-400 shadow-sm group-hover:text-blue-500"
														>
															<FeatherIcon
																name="image"
																class="h-8 w-8"
															/>
														</div>
														<div>
															<p
																class="text-sm font-medium text-gray-700"
															>
																{{ __("Add a product image") }}
															</p>
															<p class="mt-1 text-xs text-gray-500">
																{{
																	__(
																		"Click to browse or drop a file here"
																	)
																}}
															</p>
														</div>
													</div>

													<!-- Hover affordance once an image exists -->
													<div
														v-if="form.image"
														class="absolute inset-0 flex items-center justify-center bg-gray-900/0 opacity-0 transition group-hover:bg-gray-900/40 group-hover:opacity-100"
													>
														<span
															class="flex items-center gap-2 rounded-lg bg-white/95 px-3 py-2 text-sm font-medium text-gray-800 shadow"
														>
															<FeatherIcon
																name="refresh-cw"
																class="h-4 w-4"
															/>
															{{ __("Change") }}
														</span>
													</div>
												</button>

												<div
													class="mt-3 flex flex-wrap items-center gap-2"
												>
													<Button
														@click="fileInput?.click()"
														variant="outline"
													>
														<template #prefix>
															<FeatherIcon
																:name="
																	form.image
																		? 'refresh-cw'
																		: 'upload'
																"
																class="h-4 w-4"
															/>
														</template>
														{{
															form.image
																? __("Change")
																: __("Upload")
														}}
													</Button>
													<Button
														v-if="form.image"
														@click="clearImage"
														variant="subtle"
														theme="red"
													>
														<template #prefix>
															<FeatherIcon
																name="trash-2"
																class="h-4 w-4"
															/>
														</template>
														{{ __("Remove") }}
													</Button>
												</div>

												<p
													v-if="selectedFile"
													class="mt-2 flex items-center gap-2 text-sm text-blue-600"
												>
													<FeatherIcon
														name="file"
														class="h-4 w-4 flex-shrink-0"
													/>
													<span class="truncate"
														>{{ selectedFile.name }} ({{
															formatFileSize(selectedFile.size)
														}})</span
													>
												</p>
												<p
													v-if="validationErrors.image"
													class="mt-2 text-xs text-red-600"
												>
													{{ validationErrors.image }}
												</p>
												<p
													v-if="imagesDisabledBySite"
													class="mt-2 text-xs text-amber-700"
												>
													{{
														__(
															"No image file types are currently allowed. Add an image extension under Allowed File Extensions in System Settings."
														)
													}}
												</p>
												<p v-else class="mt-2 text-xs text-gray-500">
													{{
														__(
															"Allowed file types: {0} — up to {1}.",
															[
																allowedExtensionsLabel,
																maxImageSizeLabel,
															]
														)
													}}
													<br />
													{{
														__(
															"These are configurable in System Settings. Upload happens when the product is saved."
														)
													}}
												</p>
											</aside>

											<!-- ============ FIELDS ============ -->
											<div class="min-w-0 space-y-8">
												<!-- Details -->
												<section>
													<h4
														class="mb-4 text-xs font-semibold uppercase tracking-wide text-gray-500"
													>
														{{ __("Details") }}
													</h4>
													<div class="space-y-5">
														<div>
															<FormControl
																type="text"
																:label="__('Product Name')"
																v-model="form.item_name"
																:required="true"
															/>
															<p
																v-if="validationErrors.item_name"
																class="mt-1 text-xs text-red-600"
															>
																{{ validationErrors.item_name }}
															</p>
														</div>

														<div
															class="grid grid-cols-1 gap-5 min-[1536px]:grid-cols-2"
														>
															<div>
																<label
																	class="mb-1.5 block text-start text-sm font-medium text-gray-700"
																>
																	{{ __("Item Group") }}
																	<span class="text-red-500"
																		>*</span
																	>
																</label>
																<SelectInput
																	v-model="form.item_group"
																	:options="rawItemGroupOptions"
																	:placeholder="
																		__('Select Item Group')
																	"
																	:searchable="true"
																	:search-placeholder="
																		__('Search item groups...')
																	"
																/>
																<p
																	v-if="
																		validationErrors.item_group
																	"
																	class="mt-1 text-xs text-red-600"
																>
																	{{
																		validationErrors.item_group
																	}}
																</p>
															</div>
															<div>
																<label
																	class="mb-1.5 block text-start text-sm font-medium text-gray-700"
																>
																	{{ __("UOM") }}
																	<span class="text-red-500"
																		>*</span
																	>
																</label>
																<SelectInput
																	v-model="form.stock_uom"
																	:options="uomOptions"
																	:placeholder="__('Select UOM')"
																	:searchable="true"
																	:search-placeholder="
																		__('Search UOMs...')
																	"
																/>
																<p
																	v-if="
																		validationErrors.stock_uom
																	"
																	class="mt-1 text-xs text-red-600"
																>
																	{{
																		validationErrors.stock_uom
																	}}
																</p>
															</div>
															<div>
																<FormControl
																	type="number"
																	:label="priceLabel"
																	v-model="form.price"
																	:required="true"
																/>
																<p
																	v-if="validationErrors.price"
																	class="mt-1 text-xs text-red-600"
																>
																	{{ validationErrors.price }}
																</p>
															</div>
														</div>
													</div>
												</section>

												<!-- UOM Conversions -->
												<section class="border-t pt-6">
													<div
														class="mb-4 flex flex-wrap items-start justify-between gap-3"
													>
														<div>
															<h4
																class="text-xs font-semibold uppercase tracking-wide text-gray-500"
															>
																{{ __("UOM Conversions") }}
															</h4>
															<p class="mt-1 text-xs text-gray-500">
																{{
																	__(
																		"Define alternate selling units against the base UOM."
																	)
																}}
															</p>
														</div>
														<Button
															@click="addUomConversion"
															variant="outline"
														>
															<template #prefix>
																<FeatherIcon
																	name="plus"
																	class="h-4 w-4"
																/>
															</template>
															{{ __("Add UOM") }}
														</Button>
													</div>

													<div
														v-if="form.uom_conversions.length === 0"
														class="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-500"
													>
														{{ __("No alternate UOMs configured.") }}
													</div>
													<div v-else class="space-y-2">
														<div
															v-for="(
																row, index
															) in form.uom_conversions"
															:key="index"
															class="grid grid-cols-[minmax(0,1fr)_8rem_auto] items-end gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3"
														>
															<div class="min-w-0">
																<label
																	class="mb-1.5 block text-start text-xs font-medium text-gray-600"
																	>{{ __("UOM") }}</label
																>
																<SelectInput
																	v-model="row.uom"
																	:options="uomOptions"
																	:placeholder="__('Select UOM')"
																	:searchable="true"
																	:search-placeholder="
																		__('Search UOMs...')
																	"
																/>
															</div>
															<FormControl
																type="number"
																:label="__('Factor')"
																v-model="row.conversion_factor"
															/>
															<Button
																@click="removeUomConversion(index)"
																variant="subtle"
																theme="red"
																:aria-label="__('Remove')"
															>
																<FeatherIcon
																	name="trash-2"
																	class="h-4 w-4"
																/>
															</Button>
														</div>
													</div>
													<p
														v-if="validationErrors.uom_conversions"
														class="mt-2 text-xs text-red-600"
													>
														{{ validationErrors.uom_conversions }}
													</p>
													<p class="mt-2 text-xs text-gray-500">
														{{
															__(
																"Example: if base UOM is Piece, Box factor 12 means 1 Box = 12 Pieces."
															)
														}}
													</p>
												</section>

												<!-- Options -->
												<section class="border-t pt-6">
													<h4
														class="mb-4 text-xs font-semibold uppercase tracking-wide text-gray-500"
													>
														{{ __("Options") }}
													</h4>
													<div
														class="grid grid-cols-1 gap-3 min-[1536px]:grid-cols-2"
													>
														<label
															class="flex cursor-pointer items-start gap-3 rounded-lg border border-gray-200 p-3 transition-colors hover:border-gray-300 hover:bg-gray-50"
														>
															<input
																type="checkbox"
																v-model="form.is_stock_item"
																class="mt-0.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
															/>
															<span class="text-start">
																<span
																	class="block text-sm font-medium text-gray-800"
																	>{{
																		__("Maintain Stock")
																	}}</span
																>
																<span
																	class="mt-0.5 block text-xs text-gray-500"
																	>{{
																		__(
																			"Track quantity on hand for this product."
																		)
																	}}</span
																>
															</span>
														</label>
														<label
															class="flex cursor-pointer items-start gap-3 rounded-lg border border-gray-200 p-3 transition-colors hover:border-gray-300 hover:bg-gray-50"
														>
															<input
																type="checkbox"
																v-model="form.disabled"
																class="mt-0.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
															/>
															<span class="text-start">
																<span
																	class="block text-sm font-medium text-gray-800"
																	>{{ __("Disabled") }}</span
																>
																<span
																	class="mt-0.5 block text-xs text-gray-500"
																	>{{
																		__(
																			"Hide this product from the POS."
																		)
																	}}</span
																>
															</span>
														</label>
													</div>
												</section>
											</div>
										</div>
									</div>
								</div>
							</template>
						</div>
					</div>
				</div>
			</div>
		</div>
	</Transition>
</template>

<script setup>
import { Badge, Button, FormControl, LoadingIndicator, FeatherIcon } from "frappe-ui";
import SelectInput from "@/components/common/SelectInput.vue";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency";
import { useToast } from "@/composables/useToast";
import { call } from "@/utils/apiWrapper";
import { useItemSearchStore } from "@/stores/itemSearch";

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

// Upload rules belong to the site, not to this screen — see
// get_product_image_settings(). This is only the fallback used before the
// first fetch resolves, or if it fails.
const DEFAULT_IMAGE_SETTINGS = {
	extensions: ["JPG", "JPEG", "PNG", "GIF", "WEBP"],
	mime_types: ["image/gif", "image/jpeg", "image/png", "image/webp"],
	max_file_size: 25 * 1024 * 1024,
	restricted_by_system_settings: false,
};

const props = defineProps({
	modelValue: Boolean,
	posProfile: {
		type: String,
		required: true,
	},
	company: String,
	currency: String,
});

const emit = defineEmits(["update:modelValue"]);
const { showSuccess, showError, handleError } = useToast();
const itemStore = useItemSearchStore();

// State
const show = ref(props.modelValue);
const loading = ref(false);
const loadingMore = ref(false);
const saveLoading = ref(false);
const products = ref([]);
const hasMore = ref(false);
const productOffset = ref(0);
const itemGroups = ref([]);
const uoms = ref([]);
const searchQuery = ref("");
const filterGroup = ref("All");

const selectedProduct = ref(null);
const isCreating = ref(false);
const selectedFile = ref(null);
const fileInput = ref(null);
const isDraggingImage = ref(false);
const imageSettings = ref({ ...DEFAULT_IMAGE_SETTINGS });

/** Drives the mobile master-detail swap: list, or form, never both. */
const isFormOpen = computed(() => Boolean(selectedProduct.value) || isCreating.value);

const allowedExtensions = computed(() => imageSettings.value.extensions || []);
const imagesDisabledBySite = computed(() => allowedExtensions.value.length === 0);

/** `accept` for the picker: MIME types plus dotted extensions, since browsers
 *  differ on which they match. */
const imageAccept = computed(() =>
	[
		...(imageSettings.value.mime_types || []),
		...allowedExtensions.value.map((ext) => `.${ext.toLowerCase()}`),
	].join(",")
);

const maxImageSizeLabel = computed(() => formatFileSize(imageSettings.value.max_file_size || 0));

const allowedExtensionsLabel = computed(() =>
	allowedExtensions.value.map((ext) => ext.toUpperCase()).join(", ")
);
const validationErrors = ref({});
let productSearchTimer = null;

const form = ref({
	item_code: "",
	item_name: "",
	item_group: "",
	stock_uom: "Nos",
	price: 0,
	image: "",
	disabled: false,
	is_stock_item: true,
	uom_conversions: [],
});

// Computed
const rawItemGroupOptions = computed(() => {
	return itemGroups.value
		.filter((g) => !Number(g.is_group || 0))
		.map((g) => ({ label: g.name, value: g.name }));
});

const itemGroupOptions = computed(() => {
	return [{ label: __("All Groups"), value: "All" }, ...rawItemGroupOptions.value];
});

const uomOptions = computed(() => {
	return uoms.value.map((u) => ({ label: u.name, value: u.name }));
});

const priceLabel = computed(() => {
	return props.currency ? __("Price ({0})", [props.currency]) : __("Price");
});

const hasActiveProductFilters = computed(() => {
	return Boolean(searchQuery.value.trim()) || filterGroup.value !== "All";
});

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency);
}

// Watchers
watch(
	() => props.modelValue,
	(val) => {
		show.value = val;
		if (val) {
			refreshProducts();
			loadItemGroups();
			loadUOMs();
			loadImageSettings();
		}
	}
);

watch(show, (val) => {
	emit("update:modelValue", val);
	if (!val) {
		clearProductSearchTimer();
		returnToList();
	}
});

watch([searchQuery, filterGroup], () => {
	if (show.value) {
		queueProductsLoad();
	}
});

watch(
	() => form.value.item_name,
	() => clearValidationError("item_name")
);
watch(
	() => form.value.item_group,
	() => clearValidationError("item_group")
);
watch(
	() => form.value.stock_uom,
	() => clearValidationError("stock_uom")
);
watch(
	() => form.value.price,
	() => clearValidationError("price")
);

onBeforeUnmount(() => {
	clearProductSearchTimer();
});

// Actions
function handleClose() {
	show.value = false;
}

function returnToList() {
	selectedProduct.value = null;
	isCreating.value = false;
	resetForm();
}

function resetForm() {
	form.value = {
		item_code: "",
		item_name: "",
		item_group: getDefaultItemGroup(),
		stock_uom: "Nos",
		price: 0,
		image: "",
		disabled: false,
		is_stock_item: true,
		uom_conversions: [],
	};
	selectedFile.value = null;
	validationErrors.value = {};
	if (fileInput.value) fileInput.value.value = "";
}

function selectProduct(product) {
	selectedProduct.value = product;
	isCreating.value = false;
	form.value = {
		item_code: product.name,
		item_name: product.item_name,
		item_group: product.item_group,
		stock_uom: product.stock_uom,
		price: product.price,
		image: product.image || "",
		disabled: Boolean(product.disabled),
		is_stock_item: Boolean(product.is_stock_item),
		uom_conversions: (product.uom_conversions || []).map((row) => ({
			uom: row.uom,
			conversion_factor: row.conversion_factor || 1,
		})),
	};
	selectedFile.value = null;
	validationErrors.value = {};
	if (fileInput.value) fileInput.value.value = "";
}

function handleCreateNew() {
	selectedProduct.value = null;
	isCreating.value = true;
	resetForm();
}

function getDefaultItemGroup() {
	return rawItemGroupOptions.value[0]?.value || "";
}

function acceptImageFile(file) {
	clearValidationError("image");
	if (!file) return;

	const imageError = validateImageFile(file);
	if (imageError) {
		selectedFile.value = null;
		validationErrors.value = {
			...validationErrors.value,
			image: imageError,
		};
		if (fileInput.value) fileInput.value.value = "";
		showError(imageError);
		return;
	}

	selectedFile.value = file;
	const reader = new FileReader();
	reader.onload = (e) => {
		form.value.image = e.target.result;
	};
	reader.readAsDataURL(file);
}

function handleImageSelect(event) {
	acceptImageFile(event.target.files?.[0]);
}

function handleImageDrop(event) {
	isDraggingImage.value = false;
	acceptImageFile(event.dataTransfer?.files?.[0]);
}

function clearImage() {
	form.value.image = "";
	selectedFile.value = null;
	if (fileInput.value) fileInput.value.value = "";
}

function viewOnDesk() {
	if (!form.value.item_code) return;
	const encodedItem = encodeURIComponent(form.value.item_code);
	window.open(`/app/item/${encodedItem}`, "_blank", "noopener,noreferrer");
}

function addUomConversion() {
	form.value.uom_conversions.push({
		uom: "",
		conversion_factor: 1,
	});
}

function removeUomConversion(index) {
	form.value.uom_conversions.splice(index, 1);
}

function buildSavedProduct(itemCode) {
	return {
		name: itemCode,
		item_name: form.value.item_name,
		item_group: form.value.item_group,
		stock_uom: form.value.stock_uom,
		price: Number(form.value.price || 0),
		image: form.value.image || "",
		disabled: form.value.disabled ? 1 : 0,
		is_stock_item: form.value.is_stock_item ? 1 : 0,
		uom_conversions: form.value.uom_conversions.map((row) => ({
			uom: row.uom,
			conversion_factor: row.conversion_factor || 1,
		})),
	};
}

function productMatchesCurrentFilters(product) {
	if (product.disabled) {
		return false;
	}

	if (filterGroup.value !== "All" && product.item_group !== filterGroup.value) {
		return false;
	}

	const query = searchQuery.value.trim().toLowerCase();
	if (!query) return true;

	return [product.name, product.item_name, product.item_group]
		.filter(Boolean)
		.some((value) => value.toLowerCase().includes(query));
}

function syncSavedProductToList(itemCode) {
	const savedProduct = buildSavedProduct(itemCode);
	const existingIndex = products.value.findIndex((product) => product.name === itemCode);

	if (!productMatchesCurrentFilters(savedProduct)) {
		if (existingIndex >= 0) {
			products.value.splice(existingIndex, 1);
		}
		return;
	}

	if (existingIndex >= 0) {
		products.value.splice(existingIndex, 1, savedProduct);
		return;
	}

	products.value.unshift(savedProduct);
}

function clearValidationError(field) {
	if (!validationErrors.value[field]) return;
	const nextErrors = { ...validationErrors.value };
	delete nextErrors[field];
	validationErrors.value = nextErrors;
}

function validateImageFile(file) {
	if (imagesDisabledBySite.value) {
		return __("No image file types are allowed by System Settings.");
	}

	// Match on extension, not MIME type: browsers report inconsistent types for
	// the same file, and the server validates on extension too.
	const extension = (file.name.split(".").pop() || "").toUpperCase();
	if (!allowedExtensions.value.includes(extension)) {
		return __("Image must be one of: {0}", [allowedExtensionsLabel.value]);
	}

	const maxBytes = imageSettings.value.max_file_size || 0;
	if (maxBytes && file.size > maxBytes) {
		return __("Image must be {0} or smaller", [maxImageSizeLabel.value]);
	}

	return "";
}

function formatFileSize(size) {
	if (size >= 1024 * 1024) {
		return `${(size / (1024 * 1024)).toFixed(1)} MB`;
	}
	return `${Math.max(Math.round(size / 1024), 1)} KB`;
}

function validateProductForm() {
	const errors = {};
	const itemName = form.value.item_name?.trim();
	const price = Number(form.value.price);

	if (!itemName) {
		errors.item_name = __("Product Name is required");
	}

	if (!form.value.item_group) {
		errors.item_group = __("Item Group is required");
	}

	if (!form.value.stock_uom) {
		errors.stock_uom = __("UOM is required");
	}

	if (form.value.price === "" || form.value.price === null || form.value.price === undefined) {
		errors.price = __("Price is required");
	} else if (Number.isNaN(price) || price < 0) {
		errors.price = __("Price must be zero or greater");
	}

	const invalidConversion = form.value.uom_conversions.find(
		(row) => row.uom && Number(row.conversion_factor || 0) <= 0
	);
	if (invalidConversion) {
		errors.uom_conversions = __("UOM conversion factor must be greater than zero");
	}

	if (selectedFile.value) {
		const imageError = validateImageFile(selectedFile.value);
		if (imageError) {
			errors.image = imageError;
		}
	}

	validationErrors.value = errors;

	if (Object.keys(errors).length > 0) {
		showError(__("Please fix the highlighted fields"));
		return false;
	}

	return true;
}

async function uploadImage(itemCode) {
	if (!selectedFile.value) return form.value.image;

	const formData = new FormData();
	formData.append("file", selectedFile.value, selectedFile.value.name);
	formData.append("is_private", "0");
	formData.append("folder", "Home/Attachments");
	formData.append("doctype", "Item");
	formData.append("docname", itemCode);
	formData.append("fieldname", "image");

	const response = await fetch("/api/method/upload_file", {
		method: "POST",
		headers: {
			"X-Frappe-CSRF-Token": window.csrf_token,
		},
		body: formData,
	});
	const responseData = await response.json().catch(() => ({}));

	if (!response.ok || responseData.exc) {
		throw new Error(__("Image upload failed"));
	}

	if (responseData.message?.file_url) {
		return responseData.message.file_url;
	}

	throw new Error(__("Image upload did not return a file URL"));
}

async function saveProduct() {
	if (!validateProductForm()) {
		return;
	}

	saveLoading.value = true;
	try {
		const payload = { ...form.value };

		// 1. Save product
		const result = await call("pos_next.api.product_management.save_product", {
			pos_profile: props.posProfile,
			data: JSON.stringify(payload),
		});

		const itemCode = result.item_code;

		// 2. Upload image if selected
		if (selectedFile.value) {
			const fileUrl = await uploadImage(itemCode);
			if (fileUrl !== form.value.image) {
				// Update item with image url
				await call("pos_next.api.product_management.update_product_image", {
					pos_profile: props.posProfile,
					item_code: itemCode,
					file_url: fileUrl,
				});
			}
			form.value.image = fileUrl;
		}

		showSuccess(__("Product saved successfully"));
		await loadProducts();
		syncSavedProductToList(itemCode);
		selectedProduct.value = buildSavedProduct(itemCode);
		form.value.item_code = itemCode;
		isCreating.value = false;
		selectedFile.value = null;
		if (fileInput.value) fileInput.value.value = "";

		// Refresh itemStore to ensure POS UI gets updated items
		itemStore.invalidateCache();
		await itemStore.refreshItem(itemCode, props.posProfile);
	} catch (error) {
		handleError(error, __("Failed to save product"));
	} finally {
		saveLoading.value = false;
	}
}

// Data loading
function clearProductSearchTimer() {
	if (productSearchTimer) {
		clearTimeout(productSearchTimer);
		productSearchTimer = null;
	}
}

function queueProductsLoad() {
	clearProductSearchTimer();
	productSearchTimer = setTimeout(() => {
		productSearchTimer = null;
		loadProducts();
	}, SEARCH_DEBOUNCE_MS);
}

function refreshProducts() {
	clearProductSearchTimer();
	loadProducts();
}

async function loadProducts({ append = false } = {}) {
	const nextStart = append ? productOffset.value : 0;
	if (append) {
		loadingMore.value = true;
	} else {
		loading.value = true;
	}

	try {
		const params = {
			pos_profile: props.posProfile,
			start: nextStart,
			limit: PAGE_SIZE,
		};
		const searchTerm = searchQuery.value.trim();
		if (searchTerm) params.search_term = searchTerm;
		if (filterGroup.value !== "All") params.item_group = filterGroup.value;

		const data = await call("pos_next.api.product_management.get_products", params);
		const page = Array.isArray(data) ? data : [];
		const visibleProducts = page.slice(0, PAGE_SIZE);
		hasMore.value = page.length > PAGE_SIZE;
		products.value = append ? [...products.value, ...visibleProducts] : visibleProducts;
		productOffset.value = nextStart + visibleProducts.length;
	} catch (error) {
		handleError(error, __("Failed to load products"));
	} finally {
		if (append) {
			loadingMore.value = false;
		} else {
			loading.value = false;
		}
	}
}

async function loadMoreProducts() {
	if (!hasMore.value || loadingMore.value || loading.value) return;
	await loadProducts({ append: true });
}

async function loadItemGroups() {
	try {
		const data = await call("pos_next.api.product_management.get_item_groups", {
			pos_profile: props.posProfile,
		});
		itemGroups.value = data || [];
		if (isCreating.value && !form.value.item_group) {
			form.value.item_group = getDefaultItemGroup();
		}
	} catch (error) {
		handleError(error, __("Failed to load item groups"));
	}
}

async function loadImageSettings() {
	try {
		const data = await call("pos_next.api.product_management.get_product_image_settings");
		if (data) imageSettings.value = data;
	} catch (error) {
		// Non-fatal: fall back to defaults so the screen still works. The server
		// validates on upload regardless.
		console.warn("Failed to load image settings, using defaults", error);
	}
}

async function loadUOMs() {
	try {
		const data = await call("frappe.client.get_list", {
			doctype: "UOM",
			fields: ["name"],
			limit_page_length: 500,
			order_by: "name asc",
		});
		uoms.value = data || [];
	} catch (error) {
		handleError(error, __("Failed to load UOMs"));
	}
}
</script>

<style scoped>
.z-\[300\] {
	z-index: 300;
}
</style>
