<template>
	<Dialog v-model="showDialog" :options="{ title: __('Create Return Invoice'), size: '5xl' }">
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- Offline Mode Warning -->
				<div
					v-if="isOffline"
					class="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3"
				>
					<div
						class="flex-shrink-0 w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center"
					>
						<FeatherIcon name="wifi-off" class="w-5 h-5 text-amber-600" />
					</div>
					<div class="flex-1 min-w-0 text-start">
						<h4 class="text-sm font-bold text-amber-900">{{ __("Offline Mode") }}</h4>
						<p class="text-xs text-amber-700 mt-1">
							{{
								__(
									"Return invoices cannot be processed while offline. Please connect to the internet to search for invoices and create returns."
								)
							}}
						</p>
					</div>
				</div>

				<!-- Recent Invoices List -->
				<div>
					<label class="block text-sm text-start font-medium text-gray-700 mb-3">
						{{ __("Select Invoice to Return") }}
					</label>

					<!-- Smart Search Input with Autocomplete -->
					<div class="mb-3 flex gap-2">
						<div class="flex-1 relative">
							<div class="relative">
								<FeatherIcon
									name="search"
									class="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"
								/>
								<input
									ref="invoiceSearchInput"
									v-model="invoiceListFilter"
									type="text"
									:placeholder="
										isOffline
											? __('Search unavailable offline')
											: __('Search by invoice, customer, or mobile...')
									"
									:disabled="isOffline"
									:class="[
										'w-full ps-10 pe-10 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
										isOffline
											? 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
											: 'border-gray-300',
									]"
									@input="onSearchInput"
									@keydown.down.prevent="navigateSuggestion(1)"
									@keydown.up.prevent="navigateSuggestion(-1)"
									@keydown.enter.prevent="selectSuggestionOrSearch"
									@keydown.escape="closeSuggestions"
									@focus="showSuggestionsOnFocus"
									@blur="onSearchBlur"
									autocomplete="off"
								/>
								<button
									v-if="invoiceListFilter"
									@mousedown.prevent="clearSearch"
									class="absolute end-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
								>
									<FeatherIcon name="x" class="w-4 h-4" />
								</button>
							</div>

							<!-- Autocomplete Suggestions Dropdown -->
							<div
								v-if="
									showSuggestions &&
									(searchSuggestions.length > 0 ||
										searchInvoiceByNumberResource.loading)
								"
								class="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto"
							>
								<!-- Loading indicator for server search -->
								<div
									v-if="searchInvoiceByNumberResource.loading"
									class="px-3 py-2 flex items-center gap-2 text-blue-600 bg-blue-50"
								>
									<FeatherIcon name="loader" class="w-4 h-4 animate-spin" />
									<span class="text-sm font-medium">{{
										__("Searching database...")
									}}</span>
								</div>
								<!-- Suggestion list -->
								<div
									v-for="(suggestion, index) in searchSuggestions"
									:key="suggestion.name"
									@mousedown.prevent="selectSuggestion(suggestion)"
									:class="[
										'px-3 py-2 cursor-pointer transition-colors border-b border-gray-100 last:border-b-0',
										index === selectedSuggestionIndex
											? 'bg-blue-50'
											: 'hover:bg-gray-50',
									]"
								>
									<div class="flex items-center justify-between">
										<div class="flex-1 min-w-0">
											<div class="flex items-center gap-2">
												<span
													class="text-sm font-medium text-gray-900"
													v-html="
														highlightSearchMatch(
															suggestion.name,
															invoiceListFilter
														)
													"
												></span>
												<span
													:class="[
														'px-1.5 py-0.5 text-xs font-medium rounded',
														getInvoiceStatusColor(suggestion),
													]"
												>
													{{ __(suggestion.status) }}
												</span>
											</div>
											<p class="text-xs text-gray-500 truncate">
												<span
													v-html="
														highlightSearchMatch(
															suggestion.customer_name,
															invoiceListFilter
														)
													"
												></span>
												<span
													v-if="suggestion.contact_mobile"
													class="text-gray-400"
												>
													•
													<span
														v-html="
															highlightSearchMatch(
																suggestion.contact_mobile,
																invoiceListFilter
															)
														"
													></span
												></span>
											</p>
										</div>
										<div class="text-end ms-2">
											<p class="text-sm font-medium text-gray-900">
												{{ formatCurrency(suggestion.grand_total) }}
											</p>
											<p class="text-xs text-gray-400">
												{{ formatDate(suggestion.posting_date) }}
											</p>
										</div>
									</div>
								</div>
							</div>
						</div>
						<Button
							variant="subtle"
							@click="loadInvoicesResource.reload()"
							:loading="loadInvoicesResource.loading"
							:disabled="isOffline"
							:title="isOffline ? __('Refresh unavailable offline') : __('Refresh')"
						>
							<FeatherIcon name="refresh-cw" class="w-4 h-4" />
						</Button>
					</div>

					<!-- Loading State - Skeleton Loader -->
					<div v-if="loadInvoicesResource.loading" class="flex flex-col gap-2 pe-2">
						<div
							v-for="i in 4"
							:key="i"
							class="skeleton-card bg-white border border-gray-200 rounded-lg p-3"
						>
							<div class="flex items-start gap-3">
								<!-- Avatar skeleton -->
								<div
									class="skeleton-pulse w-10 h-10 rounded-full bg-gray-200 flex-shrink-0"
								></div>
								<!-- Content skeleton -->
								<div class="flex-1 min-w-0">
									<div class="flex items-center gap-2 mb-2">
										<div
											class="skeleton-pulse h-4 w-32 bg-gray-200 rounded"
										></div>
										<div
											class="skeleton-pulse h-5 w-16 bg-gray-200 rounded-full"
										></div>
									</div>
									<div
										class="skeleton-pulse h-3 w-24 bg-gray-200 rounded mb-1"
									></div>
									<div class="skeleton-pulse h-3 w-20 bg-gray-200 rounded"></div>
								</div>
								<!-- Amount skeleton -->
								<div
									class="skeleton-pulse h-5 w-16 bg-gray-200 rounded flex-shrink-0"
								></div>
							</div>
						</div>
					</div>

					<!-- Invoice List -->
					<div v-else class="max-h-96 overflow-y-auto flex flex-col gap-2 pe-2">
						<div
							v-for="invoice in filteredInvoiceList"
							:key="invoice.name"
							@click="openReturnModal(invoice)"
							class="bg-white border border-gray-200 rounded-lg p-3 hover:border-blue-400 hover:bg-blue-50/30 cursor-pointer transition-all"
						>
							<div class="flex items-start justify-between gap-3">
								<!-- Invoice Info (Start Side) -->
								<div class="flex-1 min-w-0">
									<div class="flex items-center gap-2 flex-wrap">
										<h4 class="text-sm font-bold text-gray-900">
											{{ invoice.name }}
										</h4>
										<span
											:class="[
												'px-2 py-0.5 text-xs font-semibold rounded-full whitespace-nowrap',
												getInvoiceStatusColor(invoice),
											]"
										>
											{{ __(invoice.status) }}
										</span>
									</div>
									<p class="text-xs text-gray-600 mt-1 text-start">
										{{ invoice.customer_name }}
										<span v-if="invoice.contact_mobile" class="text-gray-400">
											• {{ invoice.contact_mobile }}</span
										>
									</p>
									<p class="text-xs text-gray-500 text-start">
										{{ formatDate(invoice.posting_date) }}
									</p>
								</div>
								<!-- Amount (End Side) -->
								<div class="text-end flex-shrink-0">
									<p class="text-sm font-bold text-gray-900">
										{{ formatCurrency(invoice.grand_total) }}
									</p>
								</div>
							</div>
						</div>
						<!-- Searching Indicator -->
						<div
							v-if="
								searchInvoiceByNumberResource.loading &&
								filteredInvoiceList.length === 0
							"
							class="text-center py-12"
						>
							<div
								class="w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center mx-auto mb-4"
							>
								<FeatherIcon
									name="loader"
									class="w-8 h-8 text-blue-500 animate-spin"
								/>
							</div>
							<p class="text-sm font-medium text-gray-900 mb-1">
								{{ __("Searching...") }}
							</p>
							<p class="text-xs text-gray-500">
								{{ __("Looking for invoice in database") }}
							</p>
						</div>
						<!-- Enhanced Empty State -->
						<div
							v-else-if="
								!loadInvoicesResource.loading && filteredInvoiceList.length === 0
							"
							class="text-center py-12"
						>
							<!-- Offline Empty State -->
							<template v-if="isOffline">
								<div
									class="w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4"
								>
									<FeatherIcon name="wifi-off" class="w-8 h-8 text-amber-500" />
								</div>
								<p class="text-sm font-medium text-gray-900 mb-1 text-center">
									{{ __("No connection") }}
								</p>
								<p class="text-xs text-gray-500 text-center">
									{{ __("Connect to the internet to load invoices") }}
								</p>
							</template>
							<!-- Online Empty State -->
							<template v-else>
								<div
									class="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4"
								>
									<FeatherIcon name="file-text" class="w-8 h-8 text-gray-400" />
								</div>
								<p class="text-sm font-medium text-gray-900 mb-1 text-center">
									{{ __("No invoices found") }}
								</p>
								<p class="text-xs text-gray-500 text-center">
									{{
										__(
											"Try a different search term or check the invoice number"
										)
									}}
								</p>
							</template>
						</div>
					</div>
				</div>
			</div>
		</template>
		<template #actions>
			<Button variant="subtle" @click="showDialog = false">
				{{ __("Close") }}
			</Button>
		</template>
	</Dialog>

	<!-- Return Process Modal -->
	<Dialog v-model="returnModal.visible" :options="{ title: __('Process Return'), size: '5xl' }">
		<template #body-content>
			<div class="flex flex-col gap-4">
				<!-- Invoice Details -->
				<div
					v-if="originalInvoice"
					class="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-4 sm:p-5 border border-blue-100 shadow-sm"
				>
					<!-- Mobile Layout -->
					<div class="sm:hidden flex flex-col gap-3">
						<div class="flex items-start gap-2">
							<FeatherIcon
								name="file-text"
								class="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5"
							/>
							<div class="flex-1 min-w-0">
								<h3 class="text-base font-bold text-gray-900">
									{{ originalInvoice.name }}
								</h3>
								<span
									:class="[
										'inline-block mt-1 px-2 py-0.5 text-xs font-semibold rounded-full',
										getInvoiceStatusColor(originalInvoice),
									]"
								>
									{{ __(originalInvoice.status) }}
								</span>
							</div>
						</div>
						<div class="flex flex-col gap-2">
							<div class="text-start">
								<p class="text-xs text-gray-500">{{ __("Customer") }}</p>
								<p class="text-sm font-semibold text-gray-900">
									{{ originalInvoice.customer_name }}
								</p>
							</div>
							<div class="flex items-center justify-between">
								<div class="text-start">
									<p class="text-xs text-gray-500">{{ __("Date") }}</p>
									<p class="text-sm font-semibold text-gray-900">
										{{ formatDate(originalInvoice.posting_date) }}
									</p>
								</div>
								<div class="text-end">
									<p class="text-xs text-gray-500 mb-1">{{ __("Total") }}</p>
									<p class="text-xl font-bold text-gray-900">
										{{ formatCurrency(originalInvoice.grand_total) }}
									</p>
								</div>
							</div>
						</div>
					</div>

					<!-- Desktop Layout -->
					<div class="hidden sm:flex items-start justify-between">
						<div class="flex-1">
							<div class="flex items-center gap-2">
								<FeatherIcon name="file-text" class="w-5 h-5 text-blue-600" />
								<h3 class="text-base font-bold text-gray-900">
									{{ originalInvoice.name }}
								</h3>
								<span
									:class="[
										'px-2 py-0.5 text-xs font-semibold rounded-full',
										getInvoiceStatusColor(originalInvoice),
									]"
								>
									{{ __(originalInvoice.status) }}
								</span>
							</div>
							<div class="mt-3 grid grid-cols-2 gap-6">
								<div class="text-start">
									<p class="text-xs text-gray-500 mb-1">{{ __("Customer") }}</p>
									<p class="text-sm font-semibold text-gray-900">
										{{ originalInvoice.customer_name }}
									</p>
								</div>
								<div class="text-start">
									<p class="text-xs text-gray-500 mb-1">{{ __("Date") }}</p>
									<p class="text-sm font-semibold text-gray-900">
										{{ formatDate(originalInvoice.posting_date) }}
									</p>
								</div>
							</div>
						</div>
						<div class="text-end ms-4">
							<p class="text-xs text-gray-500 mb-1">{{ __("Total Amount") }}</p>
							<p class="text-2xl font-bold text-gray-900">
								{{ formatCurrency(originalInvoice.grand_total) }}
							</p>
						</div>
					</div>
				</div>

				<!-- Return Items -->
				<div v-if="originalInvoice">
					<div
						class="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-3 gap-2"
					>
						<label class="text-sm font-medium text-gray-700 text-start">
							{{ __("Select Items to Return") }}
						</label>
						<div class="flex gap-2 self-end sm:self-auto">
							<Button size="sm" variant="subtle" @click="selectAllFilteredItems">
								<span class="text-xs whitespace-nowrap">{{
									__("Select All")
								}}</span>
							</Button>
							<Button size="sm" variant="subtle" @click="deselectAllItems">
								<span class="text-xs whitespace-nowrap">{{
									__("Clear All")
								}}</span>
							</Button>
						</div>
					</div>

					<!-- Fast barcode return input -->
					<div class="mb-3 rounded-xl border border-blue-200 bg-blue-50 p-3">
						<div class="flex items-center justify-between gap-2 mb-2">
							<div class="text-start">
								<p class="text-xs font-bold text-blue-900">{{ __("Scan Return Barcode") }}</p>
								<p class="text-[11px] text-blue-700 mt-0.5">{{ __("Each valid scan selects or increments the return quantity. Over-return is blocked.") }}</p>
							</div>
							<span
								v-if="returnBarcodeStatus.message"
								:class="[
									'text-[11px] font-semibold px-2 py-1 rounded-full max-w-[50%] truncate',
									returnBarcodeStatus.type === 'error'
										? 'bg-red-100 text-red-700'
										: 'bg-emerald-100 text-emerald-700',
								]"
							>{{ returnBarcodeStatus.message }}</span>
						</div>
						<div class="relative">
							<FeatherIcon name="maximize" class="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-blue-500 pointer-events-none" />
							<input
								ref="returnBarcodeInput"
								v-model="returnBarcode"
								type="text"
								autocomplete="off"
								:placeholder="__('Scan barcode and press Enter...')"
								class="w-full ps-10 pe-10 py-2.5 rounded-lg border border-blue-200 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
								@keydown.enter.prevent.stop="handleReturnBarcodeScan"
							/>
							<FeatherIcon v-if="returnBarcodeBusy" name="loader" class="absolute end-3 top-1/2 -translate-y-1/2 w-4 h-4 text-blue-500 animate-spin" />
						</div>
					</div>

					<!-- Search bar for items (shown when more than 7 items) -->
					<div v-if="returnItems.length > 7" class="mb-3 relative">
						<input
							v-model="itemSearchFilter"
							type="text"
							:placeholder="__('Search items by name or code...')"
							class="w-full px-4 py-2.5 ps-10 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
						/>
						<FeatherIcon
							name="search"
							class="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
						/>
					</div>

					<div class="flex flex-col gap-2 max-h-96 overflow-y-auto pe-2">
						<div
							v-for="(item, index) in filteredReturnItems"
							:key="index"
							@click="toggleItemSelection(item)"
							:class="[
								'bg-white border rounded-lg p-3 transition-all duration-200 cursor-pointer',
								item.selected
									? 'border-blue-400 shadow-md bg-blue-50/30'
									: 'border-gray-200 hover:border-gray-300 hover:shadow-sm',
							]"
						>
							<!-- Desktop Layout -->
							<div class="hidden sm:flex items-center gap-3">
								<!-- Checkbox -->
								<input
									type="checkbox"
									v-model="item.selected"
									@click.stop
									class="h-4 w-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500 cursor-pointer"
								/>

								<!-- Item Info -->
								<div class="flex-1 min-w-0 text-start">
									<h4 class="text-sm font-bold text-gray-900 truncate">
										{{ item.item_name }}
									</h4>
									<p class="text-xs text-gray-500 mt-0.5">
										{{ item.item_code }}
									</p>
									<p
										v-if="item.already_returned > 0"
										class="text-xs text-amber-600 mt-0.5"
									>
										{{
											__("⚠️ {0} already returned", [item.already_returned])
										}}
									</p>
								</div>

								<!-- Quantity Controls -->
								<div
									class="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-1.5 border border-gray-200"
									@click.stop
								>
									<span class="text-xs font-medium text-gray-600">{{
										__("Return Qty:")
									}}</span>
									<div class="flex items-center gap-1.5">
										<button
											type="button"
											@click.stop="decrementReturnQuantity(item)"
											:disabled="!item.selected || item.return_qty <= 1"
											class="flex-shrink-0 w-8 h-8 rounded-lg bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-lg transition-colors flex items-center justify-center border border-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
										>
											−
										</button>
										<input
											v-model.number="item.return_qty"
											:max="item.quantity"
											:disabled="!item.selected"
											type="number"
											min="1"
											step="1"
											@change="normalizeItemQuantity(item)"
											@blur="normalizeItemQuantity(item)"
											class="w-12 px-1 py-1 border border-gray-300 rounded-lg text-sm text-center font-bold focus:ring-2 focus:ring-blue-500 focus:border-blue-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
										/>
										<button
											type="button"
											@click.stop="incrementReturnQuantity(item)"
											:disabled="
												!item.selected || item.return_qty >= item.quantity
											"
											class="flex-shrink-0 w-8 h-8 rounded-lg bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-lg transition-colors flex items-center justify-center border border-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
										>
											+
										</button>
									</div>
									<span class="text-xs font-semibold text-gray-700">{{
										__("of {0}", [item.quantity], "item qty")
									}}</span>
								</div>

								<!-- Rate & Amount -->
								<div class="text-center min-w-[100px]">
									<p class="text-sm font-bold text-gray-900">
										{{
											formatCurrency(
												(item.rate_with_tax || item.rate) * item.return_qty
											)
										}}
									</p>
									<p
										class="text-xs text-gray-500 mt-0.5 flex items-center gap-1 flex-wrap justify-center"
									>
										<span
											>@
											{{
												formatCurrency(item.price_list_rate || item.rate)
											}}/{{ item.uom }}</span
										>
										<span
											v-if="item.discount_per_unit > 0"
											class="inline-flex items-center px-1 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700"
											>−{{ formatCurrency(item.discount_per_unit) }}</span
										>
										<span
											v-if="
												item.tax_per_unit > 0 && item.tax_included_in_rate
											"
											class="inline-flex items-center px-1 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700"
											>{{
												__("incl. {0} tax", [
													formatCurrency(item.tax_per_unit),
												])
											}}</span
										>
										<span
											v-else-if="item.tax_per_unit > 0"
											class="inline-flex items-center px-1 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700"
											>+{{ formatCurrency(item.tax_per_unit) }}</span
										>
									</p>
								</div>
							</div>

							<!-- Mobile Layout -->
							<div class="sm:hidden flex flex-col gap-3">
								<!-- Item Header with Checkbox and Name -->
								<div class="flex items-start gap-3">
									<input
										type="checkbox"
										v-model="item.selected"
										@click.stop
										class="h-5 w-5 mt-1 text-blue-600 rounded-md focus:ring-2 focus:ring-blue-500 cursor-pointer flex-shrink-0"
									/>
									<div class="flex-1 min-w-0 text-start">
										<h4
											class="text-sm font-semibold text-gray-900 leading-tight"
										>
											{{ item.item_name }}
										</h4>
										<p class="text-xs text-gray-500 mt-1">
											{{ item.item_code }}
										</p>
										<p
											v-if="item.already_returned > 0"
											class="text-xs text-amber-600 mt-1"
										>
											{{
												__("⚠️ {0} already returned", [
													item.already_returned,
												])
											}}
										</p>
									</div>
								</div>

								<!-- Quantity Controls -->
								<div class="flex flex-col gap-2" @click.stop>
									<div class="flex items-center justify-between">
										<span
											class="text-xs font-medium text-gray-600 text-start"
											>{{ __("Return Qty:") }}</span
										>
										<span class="text-xs text-gray-500 text-end">{{
											__("of {0}", [item.quantity], "item qty")
										}}</span>
									</div>
									<div class="flex items-center gap-2">
										<button
											@click.stop="decrementReturnQuantity(item)"
											:disabled="!item.selected || item.return_qty <= 1"
											class="flex-1 h-10 rounded-lg bg-white border-2 border-gray-300 flex items-center justify-center text-gray-700 active:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed font-bold text-xl"
										>
											−
										</button>
										<input
											v-model.number="item.return_qty"
											:max="item.quantity"
											:disabled="!item.selected"
											type="number"
											min="1"
											step="1"
											@change="normalizeItemQuantity(item)"
											@blur="normalizeItemQuantity(item)"
											class="w-16 h-10 px-2 border-2 border-gray-300 rounded-lg text-lg text-center font-bold focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
										/>
										<button
											@click.stop="incrementReturnQuantity(item)"
											:disabled="
												!item.selected || item.return_qty >= item.quantity
											"
											class="flex-1 h-10 rounded-lg bg-white border-2 border-gray-300 flex items-center justify-center text-gray-700 active:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed font-bold text-xl"
										>
											+
										</button>
									</div>
								</div>

								<!-- Price -->
								<div
									class="flex items-center justify-between px-1 pt-2 border-t border-gray-100"
								>
									<span class="text-xs text-gray-600 text-start">{{
										__("Amount:")
									}}</span>
									<div class="text-end">
										<p class="text-base font-bold text-gray-900">
											{{
												formatCurrency(
													(item.rate_with_tax || item.rate) *
														item.return_qty
												)
											}}
										</p>
										<p
											class="text-xs text-gray-500 flex items-center gap-1 flex-wrap justify-end"
										>
											<span
												>@
												{{
													formatCurrency(
														item.price_list_rate || item.rate
													)
												}}/{{ item.uom }}</span
											>
											<span
												v-if="item.discount_per_unit > 0"
												class="inline-flex items-center px-1 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700"
												>−{{
													formatCurrency(item.discount_per_unit)
												}}</span
											>
											<span
												v-if="
													item.tax_per_unit > 0 &&
													item.tax_included_in_rate
												"
												class="inline-flex items-center px-1 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700"
												>{{
													__("incl. {0} tax", [
														formatCurrency(item.tax_per_unit),
													])
												}}</span
											>
											<span
												v-else-if="item.tax_per_unit > 0"
												class="inline-flex items-center px-1 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700"
												>+{{ formatCurrency(item.tax_per_unit) }}</span
											>
										</p>
									</div>
								</div>
							</div>
						</div>
					</div>
					<p v-if="returnItems.length === 0" class="text-center py-8 text-gray-500">
						{{ __("No items available for return") }}
					</p>
				</div>

				<!-- Exchange credit deliberately skips refund/provider settlement here. -->
				<div v-if="selectedItems.length > 0 && isExchangeCreditMode" class="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-start">
					<div class="flex items-start gap-3">
						<FeatherIcon name="repeat" class="w-5 h-5 text-emerald-600 mt-0.5" />
						<div>
							<p class="text-sm font-bold text-emerald-900">{{ __("Exchange Credit") }}</p>
							<p class="text-xs text-emerald-700 mt-1">{{ __("The return will remain as Customer Credit. No cash/provider refund is sent. Replacement items will continue through the normal POS checkout.") }}</p>
						</div>
					</div>
				</div>

				<!-- Payment Methods Selection -->
				<div v-if="selectedItems.length > 0 && !isExchangeCreditMode">
					<div v-if="paymentHubPlanLoading" class="bg-blue-50 rounded-xl p-3 border border-blue-200 mb-4 text-start text-xs text-blue-800">
						{{ __("Checking the original payment source before allowing this return...") }}
					</div>
					<div v-else-if="paymentHubPlanError" class="bg-red-50 rounded-xl p-3 border border-red-200 mb-4 text-start">
						<div class="text-sm font-bold text-red-900">{{ __("Payment Source Check Failed") }}</div>
						<div class="text-xs text-red-700 mt-1">{{ paymentHubPlanError }}</div>
					</div>

					<!-- Credit Sale Return Settlement -->
					<div
						v-if="isOriginalCreditSale"
						class="bg-amber-50 rounded-xl p-4 border border-amber-200 mb-4 text-start"
					>
						<h4 class="text-sm font-bold text-amber-900 mb-1">
							{{ __("Credit Sale Return") }}
						</h4>
						<p class="text-xs text-amber-800">
							{{ __("The return first reverses the customer's open receivable. Any remaining refundable value can stay as Customer Credit or, when eligible, be refunded in Cash.") }}
						</p>

						<div class="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
							<div class="rounded-lg bg-white border border-amber-200 p-2">
								<div class="text-gray-500">{{ __("A/R Reversal") }}</div>
								<div class="font-bold text-gray-900 mt-0.5">{{ formatCurrency(creditSaleArReversalAmount) }}</div>
							</div>
							<div class="rounded-lg bg-white border border-amber-200 p-2">
								<div class="text-gray-500">{{ __("Eligible Cash / Credit") }}</div>
								<div class="font-bold text-gray-900 mt-0.5">{{ formatCurrency(creditSaleRefundableExcess) }}</div>
							</div>
							<div class="rounded-lg bg-white border border-amber-200 p-2">
								<div class="text-gray-500">{{ __("Customer Credit After Return") }}</div>
								<div class="font-bold text-emerald-700 mt-0.5">{{ formatCurrency(creditSaleCustomerCreditAmount) }}</div>
							</div>
						</div>

						<label v-if="creditSaleRefundableExcess > 0" class="mt-3 flex items-start gap-3 cursor-pointer">
							<input v-model="creditSaleCashRefundEnabled" type="checkbox" class="mt-0.5 w-5 h-5 rounded border-amber-300 text-amber-600 focus:ring-amber-500" />
							<div>
								<div class="text-sm font-bold text-amber-900">{{ __("Refund Eligible Amount in Cash") }}</div>
								<div class="text-xs text-amber-700">{{ __("Cash is limited to the part of this return that exceeds the customer's current unpaid receivable.") }}</div>
							</div>
						</label>

						<div v-if="creditSaleCashRefundEnabled && creditSaleRefundableExcess > 0" class="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
							<div>
								<label class="block text-xs font-semibold text-gray-700 mb-1">{{ __("Cash Refund Amount") }}</label>
								<input v-model.number="creditSaleCashRefundAmount" type="number" min="0" :max="creditSaleRefundableExcess" step="0.001" class="w-full rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm" />
								<p class="text-[11px] text-gray-500 mt-1">{{ __("Maximum: {0}", [formatCurrency(creditSaleRefundableExcess)]) }}</p>
							</div>
							<div>
								<label class="block text-xs font-semibold text-gray-700 mb-1">{{ __("Cash Mode") }}</label>
								<select v-model="creditSaleCashMode" class="w-full rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm">
									<option value="">{{ __("Select Cash Mode") }}</option>
									<option v-for="mode in creditSaleCashModes" :key="mode" :value="mode">{{ mode }}</option>
								</select>
							</div>
							<div v-if="creditSaleManagerRequired" class="sm:col-span-2">
								<label class="block text-xs font-semibold text-gray-700 mb-1">{{ __("Manager POS PIN") }}</label>
								<input v-model="creditSaleManagerPin" type="password" inputmode="numeric" maxlength="6" autocomplete="off" class="w-full rounded-lg border border-violet-300 bg-white px-3 py-2 text-sm tracking-[0.35em]" :placeholder="__('4–6 digit PIN')" />
								<p class="text-[11px] text-violet-700 mt-1">{{ __("Manager PIN is required by POS Settings for this cash refund.") }}</p>
							</div>
						</div>
					</div>

					<!-- Add to Customer Credit Option (only for non-credit sales) -->
					<div
						v-if="!isOriginalCreditSale && !paymentHubManaged"
						class="bg-emerald-50 rounded-xl p-4 border border-emerald-200 mb-4"
					>
						<label class="flex items-start gap-3 cursor-pointer">
							<input
								type="checkbox"
								v-model="addToCustomerCredit"
								class="mt-0.5 w-5 h-5 rounded border-emerald-300 text-emerald-600 focus:ring-emerald-500 cursor-pointer"
							/>
							<div class="flex-1 text-start">
								<span class="text-sm font-bold text-emerald-900">{{
									__("Add to Customer Credit Balance")
								}}</span>
								<p class="text-xs text-emerald-700 mt-1">
									{{
										__(
											"Instead of cash refund, add the return amount to customer credit balance for future purchases."
										)
									}}
								</p>
							</div>
						</label>
					</div>

					<!-- Customer Credit Confirmation Notice -->
					<div
						v-if="addToCustomerCredit && !isOriginalCreditSale"
						class="bg-emerald-100 rounded-xl p-4 border border-emerald-300 mb-4 text-start"
					>
						<div class="flex items-center gap-2 mb-2">
							<FeatherIcon name="credit-card" class="w-5 h-5 text-emerald-600" />
							<h4 class="text-sm font-bold text-emerald-900">
								{{ __("Credit Balance") }}
							</h4>
						</div>
						<p class="text-xs text-emerald-800 mb-2">
							{{
								__(
									"The return amount will be added to the customer credit balance. No cash refund will be given."
								)
							}}
						</p>
						<div class="flex justify-between items-center text-sm">
							<span class="text-emerald-700">{{ __("Amount to Credit:") }}</span>
							<span class="font-bold text-emerald-900">{{
								formatCurrency(returnTotal)
							}}</span>
						</div>
					</div>

					<!-- Partially Paid Invoice Notice -->
					<div
						v-if="isPartiallyPaid && !isOriginalCreditSale && !addToCustomerCredit"
						class="bg-blue-50 rounded-xl p-4 border border-blue-200 mb-4 text-start"
					>
						<h4 class="text-sm font-bold text-blue-900 mb-1">
							{{ __("Partially Paid Invoice") }}
						</h4>
						<p class="text-xs text-blue-800 mb-2">
							{{
								__(
									"This invoice was partially paid. The refund will be split proportionally."
								)
							}}
						</p>
						<div class="flex flex-col gap-1 text-xs">
							<div class="flex justify-between items-center">
								<span class="text-blue-700">{{ __("Cash Refund:") }}</span>
								<span class="font-bold text-blue-900">{{
									formatCurrency(maxRefundableAmount)
								}}</span>
							</div>
							<div
								v-if="creditAdjustmentAmount > 0"
								class="flex justify-between items-center"
							>
								<span class="text-blue-700">{{ __("Credit Adjustment:") }}</span>
								<span class="font-bold text-blue-900">{{
									formatCurrency(creditAdjustmentAmount)
								}}</span>
							</div>
						</div>
					</div>

					<!-- Payment Hub refund source lock -->
					<div v-if="paymentHubManaged && !isOriginalCreditSale" class="bg-sky-50 rounded-xl p-4 border border-sky-200 mb-4 text-start">
						<div class="flex items-start gap-3">
							<FeatherIcon name="shield" class="w-5 h-5 text-sky-600 flex-shrink-0 mt-0.5" />
							<div class="flex-1">
								<h4 class="text-sm font-bold text-sky-900">{{ __("Refund to Original Payment") }}</h4>
								<p class="text-xs text-sky-800 mt-1">{{ __("Payment Hub locks the refund to the original cash, gateway, payment method and transaction. The cashier cannot change the refund source.") }}</p>
							</div>
						</div>
					</div>
					<div v-if="paymentHubLegacyProtected" class="rounded-xl border border-amber-300 bg-amber-50 p-3 mb-4 text-start">
						<div class="flex items-start gap-2"><FeatherIcon name="alert-triangle" class="w-4 h-4 text-amber-700 mt-0.5" /><div><div class="text-xs font-bold text-amber-900">{{ __("Legacy Protected Payment") }}</div><div class="text-[11px] text-amber-800 mt-0.5">{{ __("This Electronic / Physical payment is not linked to a Payment Hub provider transaction. Direct provider refund is blocked. A manager with Refund Override permission must authorize a Cash refund.") }}</div></div></div>
					</div>
					<div v-if="paymentHubManaged && requiresManagerAuthorization" class="rounded-xl border border-violet-200 bg-violet-50 p-3 mb-4 text-start">
						<div class="flex items-start gap-2"><FeatherIcon name="lock" class="w-4 h-4 text-violet-600 mt-0.5" /><div><div class="text-xs font-bold text-violet-900">{{ __("Manager / Admin Authorization Required") }}</div><div class="text-[11px] text-violet-700 mt-0.5">{{ __("Electronic and physical-terminal refunds cannot be sent until an authorized manager verifies their password.") }}</div></div></div>
					</div>
					<div v-if="hasRefundOverride" class="rounded-xl border border-orange-200 bg-orange-50 p-3 mb-4 text-start">
						<label class="block text-xs font-bold text-orange-900 mb-1">{{ __("Refund Override Reason") }} *</label>
						<input v-model="refundOverrideReason" type="text" class="w-full rounded-lg border border-orange-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" :placeholder="__('Why is the original payment method being overridden?')" />
						<p class="mt-1 text-[10px] text-orange-700">{{ __("The original provider, actual cash refund, manager and reason are permanently recorded.") }}</p>
					</div>

					<!-- Regular Payment Methods (only for non-credit sales and not adding to customer credit) -->
					<div v-if="!isOriginalCreditSale && !addToCustomerCredit">
						<div
							class="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-3 gap-2"
						>
							<label class="text-sm font-medium text-gray-700 text-start">
								{{ __("Refund Payment Methods") }}
							</label>
							<Button
								v-if="!paymentHubManaged"
								size="sm"
								variant="subtle"
								@click="addPaymentRow"
								class="self-end sm:self-auto"
							>
								<span class="text-xs">{{ __("+ Add Payment") }}</span>
							</Button>
						</div>

						<div class="flex flex-col gap-3">
							<div
								v-for="(payment, index) in refundPayments"
								:key="index"
								class="bg-white border border-gray-200 rounded-xl p-3 shadow-sm"
							>
								<!-- Desktop: Single Row | Mobile: Two Rows -->
								<div class="flex flex-col sm:flex-row sm:items-center gap-3">
									<!-- Payment Method -->
									<div class="flex items-center gap-2 flex-1">
										<div
											class="flex-shrink-0 w-10 h-10 rounded-lg bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center text-xl border border-blue-200"
										>
											{{
												payment.mode_of_payment
													? getPaymentIcon(payment.mode_of_payment)
													: "💰"
											}}
										</div>
										<div
											v-if="paymentHubManaged"
											class="flex-1 min-w-0 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2"
										>
											<div class="text-sm font-semibold text-sky-900">{{ payment.mode_of_payment }}</div>
											<div class="text-[11px] text-sky-700 truncate">
												{{ payment.provider ? `${payment.provider}${payment.actual_payment_method ? ' • ' + payment.actual_payment_method : ''}` : payment.channel }}
											</div>
											<div class="text-[10px] text-sky-600 mt-0.5">
												{{ __("Available:") }} {{ formatCurrency(payment.max_refundable || 0) }}
											</div>
											<div v-if="!payment.refund_supported && payment.warning && !payment.override_to_cash" class="text-[10px] text-red-600 mt-1">{{ payment.warning }}</div>
											<div v-if="payment.override_allowed" class="mt-2 flex flex-wrap items-center gap-2">
												<button
													type="button"
													@click="toggleRefundOverride(payment)"
													:class="[
														'rounded-md border px-2 py-1 text-[10px] font-semibold',
														payment.override_to_cash ? 'border-orange-300 bg-orange-100 text-orange-800' : 'border-gray-300 bg-white text-gray-600 hover:bg-gray-50',
													]"
												>
													{{ payment.override_to_cash ? __("Override: Refund as Cash") : __("Manager Override to Cash") }}
												</button>
												<span v-if="payment.override_to_cash" class="text-[10px] font-medium text-orange-700">
													{{ __("Actual refund:") }} {{ payment.override_mode_of_payment }}
												</span>
											</div>
										</div>
										<select
											v-else
											v-model="payment.mode_of_payment"
											:style="paymentSelectStyle"
											class="payment-select flex-1 py-2.5 border border-gray-300 rounded-lg text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white appearance-none cursor-pointer hover:border-gray-400 transition-colors ps-3 pe-10"
										>
											<option value="">{{ __("Select method...") }}</option>
											<option
												v-for="method in paymentMethods"
												:key="method.mode_of_payment"
												:value="method.mode_of_payment"
											>
												{{ method.mode_of_payment }}
											</option>
										</select>
									</div>
									<!-- Amount with Counter -->
									<div class="flex items-center gap-2 flex-1">
										<button
											@click="adjustRefundPayment(payment, -1)"
											type="button"
											class="flex-shrink-0 w-10 h-10 sm:w-9 sm:h-9 rounded-lg bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-xl transition-colors flex items-center justify-center border border-gray-300"
										>
											−
										</button>
										<input
											:value="payment.amount"
											@input="updateRefundPaymentAmount(payment, $event.target.value)"
											@focus="$event.target.select()"
											type="text"
											inputmode="decimal"
											:placeholder="__('Amount')"
											class="flex-1 min-w-0 px-3 py-2.5 text-base font-bold text-center border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 hover:border-gray-400 transition-colors"
										/>
										<button
											@click="adjustRefundPayment(payment, 1)"
											type="button"
											class="flex-shrink-0 w-10 h-10 sm:w-9 sm:h-9 rounded-lg bg-gray-100 hover:bg-gray-200 active:bg-gray-300 text-gray-700 font-bold text-xl transition-colors flex items-center justify-center border border-gray-300"
										>
											+
										</button>
									</div>
									<!-- Delete Button -->
									<button
										v-if="refundPayments.length > 1 && !paymentHubManaged"
										@click="removePaymentRow(index)"
										class="hidden sm:flex flex-shrink-0 w-9 h-9 items-center justify-center text-red-500 hover:text-red-700 hover:bg-red-50 active:bg-red-100 rounded-lg transition-colors"
										:title="__('Remove')"
									>
										<FeatherIcon name="trash-2" class="w-4 h-4" />
									</button>
								</div>
								<!-- Mobile Delete Button -->
								<button
									v-if="refundPayments.length > 1 && !paymentHubManaged"
									@click="removePaymentRow(index)"
									class="sm:hidden mt-2 w-full py-2 text-sm text-red-600 hover:bg-red-50 active:bg-red-100 rounded-lg transition-colors flex items-center justify-center gap-1"
								>
									<FeatherIcon name="trash-2" class="w-4 h-4" />
									{{ __("Remove") }}
								</button>
							</div>
						</div>

						<!-- Payment Summary -->
						<div class="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
							<div class="flex items-center justify-between text-sm">
								<span class="text-gray-600">{{
									isPartiallyPaid
										? __("Refundable Amount:")
										: __("Total Refund:")
								}}</span>
								<span class="font-bold text-gray-900">{{
									formatCurrency(
										isPartiallyPaid ? maxRefundableAmount : returnTotal
									)
								}}</span>
							</div>
							<div class="flex items-center justify-between text-sm mt-1">
								<span class="text-gray-600">{{ __("Payment Total:") }}</span>
								<span
									:class="[
										'font-bold',
										Math.abs(
											totalPaymentAmount -
												(isPartiallyPaid
													? maxRefundableAmount
													: returnTotal)
										) < 0.01
											? 'text-green-600'
											: 'text-red-600',
									]"
								>
									{{ formatCurrency(totalPaymentAmount) }}
								</span>
							</div>
							<p
								v-if="
									Math.abs(
										totalPaymentAmount -
											(isPartiallyPaid ? maxRefundableAmount : returnTotal)
									) >= 0.01
								"
								class="mt-2 text-xs text-amber-600 text-start"
							>
								{{
									isPartiallyPaid
										? __("⚠️ Payment total must equal refundable amount")
										: __("⚠️ Payment total must equal refund amount")
								}}
							</p>
						</div>
					</div>
				</div>

				<!-- Return Summary -->
				<div
					v-if="selectedItems.length > 0"
					class="bg-gradient-to-br from-red-50 to-orange-50 rounded-xl p-4 sm:p-5 border border-red-200 shadow-sm"
				>
					<div class="flex items-center gap-2 mb-3">
						<FeatherIcon
							name="corner-down-left"
							class="w-5 h-5 text-red-600 flex-shrink-0"
						/>
						<h3 class="text-sm font-bold text-gray-900">{{ __("Return Summary") }}</h3>
					</div>
					<div class="flex flex-col gap-2">
						<div class="flex justify-between items-center">
							<span class="text-sm text-gray-600">{{ __("Items to Return:") }}</span>
							<span
								class="px-2 py-1 bg-white rounded-lg text-sm font-bold text-gray-900 border border-red-200"
								>{{ selectedItems.length }}</span
							>
						</div>
						<!-- Breakdown for partially paid invoices -->
						<template v-if="showPartialBreakdown">
							<div
								class="flex justify-between items-center text-sm pt-2 border-t border-red-200"
							>
								<span class="text-gray-600">{{ __("Return Value:") }}</span>
								<span class="font-medium text-gray-700">{{
									formatCurrency(returnTotal)
								}}</span>
							</div>
							<div class="flex justify-between items-center text-sm">
								<span class="text-gray-600">{{ __("Credit Adjustment:") }}</span>
								<span class="font-medium text-gray-700"
									>-{{ formatCurrency(creditAdjustmentAmount) }}</span
								>
							</div>
						</template>
						<!-- Final refund amount -->
						<div
							class="flex justify-between items-center pt-2 border-t border-red-200"
						>
							<span class="text-sm sm:text-base font-semibold text-gray-700">{{
								__(summaryRefundLabel)
							}}</span>
							<span class="text-xl sm:text-2xl font-bold text-red-600">{{
								formatCurrency(summaryRefundAmount)
							}}</span>
						</div>
					</div>
				</div>

				<!-- Return Reason -->
				<div v-if="selectedItems.length > 0">
					<label class="block text-sm font-medium text-gray-700 mb-2 text-start">
						{{ __("Return Reason") }}
						<span class="text-gray-400">({{ __("optional") }})</span>
					</label>
					<textarea
						v-model="returnReason"
						rows="3"
						:placeholder="
							__(
								'Enter reason for return (e.g., defective product, wrong item, customer request)...'
							)
						"
						class="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
					></textarea>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex flex-col w-full gap-2">
				<p v-if="submitError" class="text-xs text-red-600">{{ submitError }}</p>
				<div
					class="flex flex-col sm:flex-row sm:items-center sm:justify-between w-full gap-2 sm:gap-3"
				>
					<p
						v-if="selectedItems.length > 0"
						class="text-xs text-gray-500 flex-shrink-0 order-2 sm:order-1"
					>
						{{ __("{0} item(s) selected", [selectedItems.length]) }}
					</p>
					<div
						class="flex gap-2 w-full sm:w-auto sm:ms-auto flex-shrink-0 order-1 sm:order-2"
					>
						<Button
							variant="subtle"
							@click="closeReturnModal"
							class="flex-1 sm:flex-initial"
						>
							<span class="text-sm">{{ __("Cancel") }}</span>
						</Button>
						<Button
							v-if="paymentHubManaged && returnDraftDoc && returnRefundStatus && !returnRefundStatus.all_complete"
							variant="subtle"
							@click="handleCheckRefund"
							:disabled="isSubmitting"
						>
							<span class="text-sm whitespace-nowrap">{{ __("Check Refund") }}</span>
						</Button>
						<Button
							variant="solid"
							theme="red"
							@click="handleCreateReturn"
							:disabled="!canCreateReturn || isSubmitting"
							:loading="isSubmitting"
							class="flex-1 sm:flex-initial"
						>
							<span class="text-sm whitespace-nowrap">{{
								hasRetryableFailedRefund
									? __("Retry Refund")
									: paymentHubManaged
										? __("Refund & Create Return")
										: __("Create Return")
							}}</span>
						</Button>
					</div>
				</div>
			</div>
		</template>
	</Dialog>

	<!-- Refund manager/admin authorization -->
	<Dialog
		v-model="refundAuthDialog.visible"
		:options="{ title: __('Manager / Admin Authorization'), size: 'sm' }"
	>
		<template #body-content>
			<div class="space-y-3">
				<div class="rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs text-violet-800">
					{{ hasRefundOverride ? __("A refund-method override requires a user with Payment Hub Refund Override permission.") : __("Electronic / terminal refund requires a user with Payment Hub Refund Approver permission.") }}
				</div>
				<div>
					<label class="block text-xs font-semibold text-gray-700 mb-1">{{ __("Manager Username / Email") }}</label>
					<input v-model="refundAuthDialog.approver" type="text" autocomplete="username" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500" />
				</div>
				<div>
					<label class="block text-xs font-semibold text-gray-700 mb-1">{{ __("Password") }}</label>
					<input v-model="refundAuthDialog.password" type="password" autocomplete="current-password" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500" @keyup.enter="submitRefundAuthorization" />
				</div>
				<div>
					<label class="block text-xs font-semibold text-gray-700 mb-1">{{ __("Authorization Reason") }}</label>
					<textarea v-model="refundAuthDialog.reason" rows="2" class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"></textarea>
				</div>
				<p v-if="refundAuthDialog.error" class="text-xs text-red-600">{{ refundAuthDialog.error }}</p>
			</div>
		</template>
		<template #actions>
			<div class="flex w-full justify-end gap-2">
				<Button variant="subtle" :disabled="refundAuthDialog.loading" @click="cancelRefundAuthorization">{{ __("Cancel") }}</Button>
				<Button variant="solid" theme="blue" :loading="refundAuthDialog.loading" :disabled="refundAuthDialog.loading" @click="submitRefundAuthorization">{{ __("Authorize Refund") }}</Button>
			</div>
		</template>
	</Dialog>

	<!-- Error Dialog -->
	<Dialog v-model="errorDialog.visible" :options="{ title: errorDialog.title, size: 'sm' }">
		<template #body-content>
			<div
				class="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3"
			>
				<FeatherIcon name="alert-triangle" class="h-5 w-5 flex-shrink-0 text-red-600" />
				<div>
					<p class="text-sm font-semibold text-red-700">{{ errorDialog.title }}</p>
					<p class="mt-1 text-sm text-red-600 whitespace-pre-line">
						{{ errorDialog.message }}
					</p>
				</div>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end w-full">
				<Button variant="solid" theme="red" @click="closeErrorDialog">{{
					__("OK")
				}}</Button>
			</div>
		</template>
	</Dialog>

	<!-- Return Period Expired Dialog -->
	<Dialog
		v-model="returnExpiredDialog.visible"
		:options="{ title: __('Return Period Expired'), size: 'md' }"
	>
		<template #body-content>
			<div class="flex flex-col items-center text-center py-4">
				<!-- Clock/Calendar Icon -->
				<div
					class="w-16 h-16 rounded-full bg-orange-100 flex items-center justify-center mb-4"
				>
					<FeatherIcon name="clock" class="w-8 h-8 text-orange-600" />
				</div>

				<!-- Invoice Number -->
				<h3 class="text-lg font-bold text-gray-900 mb-2">
					{{ returnExpiredDialog.invoiceName }}
				</h3>

				<!-- Main Message -->
				<p class="text-gray-600 mb-4">
					{{
						__(
							"This invoice cannot be returned because the return period has expired."
						)
					}}
				</p>

				<!-- Details Box -->
				<div class="w-full bg-gray-50 rounded-lg p-4 space-y-2">
					<div class="flex justify-between text-sm">
						<span class="text-start text-gray-500">{{ __("Invoice Date") }}</span>
						<span class="text-end font-medium text-gray-900">{{
							returnExpiredDialog.invoiceDate
						}}</span>
					</div>
					<div class="flex justify-between text-sm">
						<span class="text-start text-gray-500">{{
							__("Days Since Purchase")
						}}</span>
						<span class="text-end font-medium text-red-600"
							>{{ returnExpiredDialog.daysSince }} {{ __("days") }}</span
						>
					</div>
					<div class="flex justify-between text-sm">
						<span class="text-start text-gray-500">{{
							__("Return Allowed Within")
						}}</span>
						<span class="text-end font-medium text-gray-900"
							>{{ returnExpiredDialog.allowedDays }} {{ __("days") }}</span
						>
					</div>
				</div>

				<!-- Help Text -->
				<p class="text-xs text-gray-500 mt-4">
					{{ __("Please contact your manager if you need to process this return.") }}
				</p>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { useOfflineStatus } from "@/composables/useOfflineStatus";
import { useToast } from "@/composables/useToast";
import { getPaymentIcon } from "@/utils/payment";
import {
	DEFAULT_CURRENCY,
	DEFAULT_LOCALE,
	formatCurrency as formatCurrencyUtil,
	roundCurrency,
} from "@/utils/currency";
import { getInvoiceStatusColor } from "@/utils/invoice";
import { call } from "@/utils/apiWrapper";
import { QueuedMutex } from "@/utils/mutex";
import { Button, Dialog, FeatherIcon, createResource } from "frappe-ui";
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";

const { showSuccess, showError, showWarning } = useToast();
const { isOffline } = useOfflineStatus();

// ============================================
// Constants (hoisted for performance)
// ============================================
const INVOICE_PATTERN = /^(ACC-SINV|SINV|SI|INV|ACC)/i;
const INVOICE_FORMAT_PATTERN = /^\d{4,}$/;
const DATE_FORMAT_OPTIONS = { year: "numeric", month: "short", day: "numeric" };
const MAX_SUGGESTIONS = 8;
const SEARCH_DEBOUNCE_MS = 300;
const MIN_SEARCH_LENGTH = 2;
const MIN_SERVER_SEARCH_LENGTH = 4;

const props = defineProps({
	modelValue: Boolean,
	posProfile: String,
	posOpeningShift: String,
	currency: { type: String, default: DEFAULT_CURRENCY },
	preselectedInvoice: { type: Object, default: null },
	settlementMode: { type: String, default: "refund" },
});

const emit = defineEmits(["update:modelValue", "return-created"]);

// Computed getter/setter for v-model pattern (per codebase standard)
const showDialog = computed({
	get: () => props.modelValue,
	set: (val) => emit("update:modelValue", val),
});

const isExchangeCreditMode = computed(() => props.settlementMode === "exchange-credit");

// State
const originalInvoice = ref(null);
// Stores the return document created by ERPNext's make_sales_return().
// Contains sales_team, taxes, and other child tables copied from the original invoice.
const preparedReturnDoc = ref(null);
const returnItems = ref([]);
const returnReason = ref("");
const paymentMethods = ref([]);
const refundPayments = ref([]);
const invoiceList = ref([]);
const invoiceListFilter = ref("");
const itemSearchFilter = ref("");
const submitError = ref("");
const isSubmitting = ref(false);
// When true, return amount is added to customer credit balance instead of cash refund
const addToCustomerCredit = ref(false);

// Fast retail barcode-return state. Scans are queued so rapid scanner input is
// never lost while the previous barcode lookup is still in flight.
const returnBarcodeInput = ref(null);
const returnBarcode = ref("");
const returnBarcodeBusy = ref(false);
const returnBarcodeStatus = reactive({ type: "", message: "" });
const returnBarcodeQueue = new QueuedMutex({ timeout: 10000, name: "InvoiceReturnBarcode" });
let returnBarcodeStatusTimer = null;

// Payment Hub return/refund state
const paymentHubPlan = ref(null);
const paymentHubPlanLoading = ref(false);
const paymentHubPlanError = ref("");
const returnDraftDoc = ref(null);
const returnRefundStatus = ref(null);
const refundOverrideReason = ref("");
let refundAuthResolve = null;
const refundAuthDialog = reactive({
	visible: false,
	loading: false,
	approver: "",
	password: "",
	reason: "",
	error: "",
	returnInvoice: null,
	refundLines: [],
});

// Autocomplete state
const invoiceSearchInput = ref(null);
const showSuggestions = ref(false);
const selectedSuggestionIndex = ref(-1);

// Invoice payment tracking
const isOriginalCreditSale = ref(false);
const isPartiallyPaid = ref(false);
const originalPaidAmount = ref(0);
const originalOutstandingAmount = ref(0);

// Credit-sale return settlement. Linked returns always reverse open A/R first.
// Any value beyond the remaining receivable can stay as Customer Credit or be
// refunded in Cash (up to the server-calculated eligible excess).
const creditSaleCashRefundEnabled = ref(false);
const creditSaleCashRefundAmount = ref(0);
const creditSaleCashMode = ref("");
const creditSaleManagerPin = ref("");
const creditSaleCashModes = ref([]);
const requireManagerPinCreditSaleCash = ref(true);

// UI state
const errorDialog = reactive({
	visible: false,
	title: __("Validation Error"),
	message: "",
});
const returnModal = reactive({ visible: false });
const returnExpiredDialog = reactive({
	visible: false,
	invoiceName: "",
	invoiceDate: "",
	daysSince: 0,
	allowedDays: 0,
});

// Resource for loading recent invoices (only those with items available for return)
const loadInvoicesResource = createResource({
	url: "pos_next.api.invoices.get_returnable_invoices",
	makeParams() {
		return {
			limit: 50,
			pos_profile: props.posProfile,
		};
	},
	auto: false,
	onSuccess(data) {
		if (data) {
			invoiceList.value = data;
		}
	},
	onError(error) {
		console.error("Error loading invoices:", error);
		showError(__("Failed to load recent invoices"));
	},
});

// Resource for searching a specific invoice by number (searches entire database)
const searchInvoiceByNumberResource = createResource({
	url: "pos_next.api.invoices.search_invoice_by_number",
	auto: false,
	onSuccess(data) {
		if (data && data.length > 0) {
			// Merge search results with existing invoice list, avoiding duplicates
			const existingNames = new Set(invoiceList.value.map((inv) => inv.name));
			const newInvoices = data.filter((inv) => !existingNames.has(inv.name));
			if (newInvoices.length > 0) {
				// Add to the beginning of the list so they appear first
				invoiceList.value = [...newInvoices, ...invoiceList.value];
			}
		}
	},
	onError(error) {
		console.error("Error searching invoice:", error);
	},
});

// Resource for loading payment methods from POS Profile
const loadPaymentMethodsResource = createResource({
	url: "frappe.client.get",
	makeParams() {
		return {
			doctype: "POS Profile",
			name: props.posProfile,
			fields: JSON.stringify(["name", "payments"]),
		};
	},
	auto: false,
	onSuccess(data) {
		if (data && data.payments) {
			paymentMethods.value = data.payments;
			// Re-initialize refund payments now that we know the current
			// profile's modes. initializePaymentsFromInvoice() may have
			// already run (from fetchInvoiceResource.onSuccess) before
			// paymentMethods were loaded — in that case it skipped the
			// foreign mode remap. Now that modes are available, re-run
			// to validate and remap any foreign modes from cross-branch
			// returns. See initializePaymentsFromInvoice() JSDoc for details.
			if (originalInvoice.value) {
				initializePaymentsFromInvoice();
			}
		}
	},
	onError(error) {
		console.error("Error loading payment methods:", error);
	},
});

// Return-security/cash options are shared with the no-invoice return flow.
// We use the same POS Settings manager-PIN switch and the current profile Cash modes.
const returnSecurityOptionsResource = createResource({
	url: "pos_next.api.retail_returns.get_no_invoice_return_options",
	auto: false,
	onSuccess(data) {
		creditSaleCashModes.value = Array.isArray(data?.cash_modes) ? data.cash_modes : [];
		requireManagerPinCreditSaleCash.value = Boolean(
			Number(data?.require_manager_pin_cash_refund ?? 1)
		);
		if (!creditSaleCashMode.value && creditSaleCashModes.value.length) {
			creditSaleCashMode.value = creditSaleCashModes.value[0];
		}
	},
	onError(error) {
		console.error("Could not load return security options:", error);
		creditSaleCashModes.value = [];
	},
});

// Resource for fetching a prepared return invoice.
// Uses ERPNext's make_sales_return() which creates a properly structured return document
// with all child tables (sales_team, taxes, etc.) copied from the original invoice.
// This ensures sales commissions are correctly reversed when processing returns.
const fetchInvoiceResource = createResource({
	url: "pos_next.api.invoices.prepare_return_invoice",
	auto: false,
	onSuccess(data) {
		if (data) {
			// Store the complete return document from make_sales_return.
			// This includes sales_team entries needed for commission reversal.
			preparedReturnDoc.value = data;

			// The API returns original invoice data in _original_invoice for reference
			const origInvoice = data._original_invoice || {};

			// Filter items that still have quantity available for return.
			// The API calculates remaining_qty by subtracting previously returned quantities.
			const availableItems = data.items.filter((item) => item.remaining_qty > 0);

			if (availableItems.length === 0) {
				showWarning(__("All items from this invoice have already been returned"));
				originalInvoice.value = null;
				preparedReturnDoc.value = null;
				returnItems.value = [];
				return;
			}

			// Store original invoice data for display in the UI
			originalInvoice.value = {
				name: data.return_against,
				customer: data.customer,
				customer_name: origInvoice.customer_name || data.customer_name,
				company: data.company,
				posting_date: origInvoice.posting_date,
				grand_total: origInvoice.grand_total,
				paid_amount: origInvoice.paid_amount,
				outstanding_amount: origInvoice.outstanding_amount,
				payments: origInvoice.payments || [],
				docstatus: 1, // Already validated by backend
				is_return: 0,
			};

			// Map items for UI display and selection.
			// - sales_invoice_item: links to original item row for accurate return tracking
			// - remaining_qty: maximum quantity user can return for this item
			returnItems.value = availableItems.map((item) => ({
				...item,
				name: item.sales_invoice_item,
				quantity: item.remaining_qty,
				selected: false,
				return_qty: item.remaining_qty,
				original_qty: item.original_qty,
			}));
			returnItems.value.forEach(normalizeItemQuantity);

			// Calculate payment totals from original invoice for refund handling
			const totalPaidFromPayments =
				origInvoice.payments?.reduce((sum, p) => sum + Math.abs(p.amount || 0), 0) || 0;
			originalPaidAmount.value = origInvoice.paid_amount || totalPaidFromPayments || 0;
			originalOutstandingAmount.value = origInvoice.outstanding_amount || 0;

			// Detect credit sale (Pay on Account): no payments recorded OR full amount outstanding.
			// Credit sales don't require cash refund - they reverse the accounts receivable.
			const hasNoPayments = !origInvoice.payments || origInvoice.payments.length === 0;
			const isFullyUnpaid =
				Math.abs(origInvoice.outstanding_amount - origInvoice.grand_total) < 0.01;
			isOriginalCreditSale.value =
				hasNoPayments || (totalPaidFromPayments < 0.01 && isFullyUnpaid);

			// Detect partial payment: some amount paid but still has outstanding balance.
			// Partial payments require proportional refund calculation.
			isPartiallyPaid.value =
				originalPaidAmount.value > 0 && originalOutstandingAmount.value > 0;

			// Load payment methods if not already loaded
			if (paymentMethods.value.length === 0 && props.posProfile) {
				loadPaymentMethodsResource.reload();
			}

			if (isExchangeCreditMode.value) {
				// Exchange returns intentionally become Customer Credit. Provider refunds
				// remain untouched and the replacement sale goes through normal checkout.
				refundPayments.value = [];
				paymentHubPlan.value = null;
				paymentHubPlanError.value = "";
				nextTick(() => returnBarcodeInput.value?.focus());
			} else {
				// Set up refund payment rows based on original invoice payments
				initializePaymentsFromInvoice();

				// Lock Payment Hub-managed returns to the original captured payment sources.
				loadPaymentHubRefundPlan();
			}
			focusReturnBarcodeInput();
		}
	},
	onError(error) {
		console.error("Error fetching invoice:", error);
		// Close the return modal since we can't proceed
		returnModal.visible = false;
		// Extract and show the actual error message (e.g., return period expired)
		const errorMsg = extractErrorMessage(error, __("Failed to load invoice details"));
		showError(errorMsg);
	},
});

// Resource for submitting the return invoice to the server
const createReturnResource = createResource({
	url: "pos_next.api.invoices.submit_invoice",
	makeParams() {
		// Use the prepared return document as the base.
		// This document was created by ERPNext's make_sales_return() and contains
		// the sales_team entries from the original invoice.
		const baseDoc = preparedReturnDoc.value || {};

		const invoiceData = {
			doctype: "Sales Invoice",
			pos_profile: props.posProfile,
			posa_pos_opening_shift: props.posOpeningShift,
			customer: baseDoc.customer || originalInvoice.value.customer,
			company: baseDoc.company || originalInvoice.value.company,
			is_return: 1,
			return_against: baseDoc.return_against || originalInvoice.value.name,
			// Setting to 0 ensures GL entries point to original invoice,
			// which reduces its outstanding amount and updates its status
			update_outstanding_for_self: 0,
			is_pos: 1,
			update_stock: 1,
			// Include sales_team from the prepared document.
			// This ensures sales commission is reversed for the returned items.
			sales_team:
				baseDoc.sales_team?.map((member) => ({
					sales_person: member.sales_person,
					allocated_percentage: member.allocated_percentage || 0,
				})) || [],
			// Build items array from user's selection with negative quantities for return
			items: selectedItems.value.map((item) => ({
				item_code: item.item_code,
				item_name: item.item_name,
				qty: -Math.abs(item.return_qty),
				rate: item.rate,
				warehouse: item.warehouse,
				uom: item.uom,
				conversion_factor: item.conversion_factor || 1,
				// Link to original invoice item row for accurate return tracking in ERPNext
				sales_invoice_item: item.name,
			})),
			// Exchange mode deliberately leaves the credit note outstanding so the
			// replacement sale can consume it as Customer Credit. It does NOT create
			// wallet credit and does NOT send a Payment Hub provider refund.
			add_to_customer_balance: isExchangeCreditMode.value ? false : addToCustomerCredit.value,
			payments: isExchangeCreditMode.value
				? []
				: isOriginalCreditSale.value
				? normalizedCreditSaleCashRefund.value > 0
					? [{
						mode_of_payment: creditSaleCashMode.value,
						amount: -Math.abs(normalizedCreditSaleCashRefund.value),
					  }]
					: []
				: addToCustomerCredit.value
				? []
				: refundPayments.value.map((payment) => ({
						mode_of_payment: payment.mode_of_payment,
						amount: -Math.abs(payment.amount),
				  })),
			remarks:
				returnReason.value ||
				(isExchangeCreditMode.value
					? __("Exchange credit against {0}", [originalInvoice.value.name])
					: __("Return against {0}", [originalInvoice.value.name])),
		};

		// Return in the correct format: invoice as JSON string
		return {
			invoice: JSON.stringify(invoiceData),
			data: JSON.stringify({
				pos_next_exchange_return: isExchangeCreditMode.value ? 1 : 0,
				credit_sale_cash_refund: isOriginalCreditSale.value && normalizedCreditSaleCashRefund.value > 0
					? {
						amount: normalizedCreditSaleCashRefund.value,
						mode_of_payment: creditSaleCashMode.value,
						manager_pin: creditSaleManagerRequired.value ? creditSaleManagerPin.value : "",
					  }
					: null,
			}),
		};
	},
	auto: false,
	transform(data) {
		// Check if the response contains an error even on "success"
		if (data && data.exc) {
			throw data;
		}
		return data;
	},
	onSuccess(data) {
		submitError.value = "";
		isSubmitting.value = false;
		const successPayload = {
			...data,
			customer: originalInvoice.value?.customer,
			customer_name: originalInvoice.value?.customer_name,
			exchange_credit: isExchangeCreditMode.value,
		};

		// Close/reset the source return modal BEFORE bubbling success. ExchangeDialog
		// can then transition to replacement items without a late child close event
		// racing the new dialog, and standalone return printing cannot leave this
		// modal/overlay visible behind the print window.
		closeReturnModal();
		emit("return-created", successPayload);

		// Reload the invoice list to remove fully returned invoices
		loadInvoicesResource.reload();
		showSuccess(__("Return invoice {0} created successfully", [data.name]));
	},
	onError(error) {
		isSubmitting.value = false;
		const errorMsg = extractErrorMessage(error);
		submitError.value = errorMsg;
		console.error("Error creating return - full error object:", error);
		openErrorDialog(errorMsg);
	},
});

// Lifecycle hooks
onMounted(() => {
	if (props.posProfile) {
		loadPaymentMethodsResource.reload();
		returnSecurityOptionsResource.fetch({ pos_profile: props.posProfile });
	}
	document.addEventListener("keydown", handleKeyboardShortcuts);
});

onUnmounted(() => {
	document.removeEventListener("keydown", handleKeyboardShortcuts);
	// Clean up any pending debounced search
	if (serverSearchTimeout) {
		clearTimeout(serverSearchTimeout);
		serverSearchTimeout = null;
	}
	if (returnBarcodeStatusTimer) {
		clearTimeout(returnBarcodeStatusTimer);
		returnBarcodeStatusTimer = null;
	}
});

// Watchers
watch(
	() => props.modelValue,
	(val) => {
		if (val) {
			// If a preselected invoice is provided, skip showing the invoice list dialog
			// and go directly to the Process Return modal
			if (props.preselectedInvoice?.name) {
				// Don't show the main dialog with invoice list - go directly to return modal
				showDialog.value = false;
				checkValidityAndOpenModal(props.preselectedInvoice.name, true);
			} else {
				// Normal flow - show the invoice selection dialog
				loadInvoicesResource.reload();
			}
		} else {
			resetForm();
		}
	}
);

// Watch for preselectedInvoice changes to handle subsequent return requests
// This handles the case when the dialog is opened again with a different invoice
watch(
	() => props.preselectedInvoice,
	(newInvoice, oldInvoice) => {
		// Only trigger if modelValue is true and we have a new invoice
		if (props.modelValue && newInvoice?.name && newInvoice.name !== oldInvoice?.name) {
			showDialog.value = false;
			checkValidityAndOpenModal(newInvoice.name, true);
		}
	}
);

// Clear search input when expired dialog closes
watch(
	() => returnExpiredDialog.visible,
	(val) => {
		if (!val) {
			invoiceListFilter.value = "";
		}
	}
);

// Computed properties
const selectedItems = computed(() =>
	returnItems.value.filter((item) => item.selected && item.return_qty > 0)
);

const filteredReturnItems = computed(() => {
	if (!itemSearchFilter.value) return returnItems.value;
	const searchTerm = itemSearchFilter.value.toLowerCase();
	return returnItems.value.filter(
		(item) =>
			item.item_name?.toLowerCase().includes(searchTerm) ||
			item.item_code?.toLowerCase().includes(searchTerm)
	);
});

const hasOpenShift = computed(() => Boolean(props.posOpeningShift));

// Use rate_with_tax (includes tax) for accurate refund calculation
const returnTotal = computed(() =>
	roundCurrency(
		selectedItems.value.reduce(
			(sum, item) =>
				sum + roundCurrency(item.return_qty * (item.rate_with_tax || item.rate)),
			0
		)
	)
);

const creditSaleArReversalAmount = computed(() =>
	roundCurrency(
		Math.min(returnTotal.value, Math.max(0, Number(originalOutstandingAmount.value || 0)))
	)
);
const creditSaleRefundableExcess = computed(() =>
	roundCurrency(Math.max(0, returnTotal.value - creditSaleArReversalAmount.value))
);
const normalizedCreditSaleCashRefund = computed(() => {
	if (!creditSaleCashRefundEnabled.value) return 0;
	return roundCurrency(
		Math.max(0, Math.min(Number(creditSaleCashRefundAmount.value || 0), creditSaleRefundableExcess.value))
	);
});
const creditSaleCustomerCreditAmount = computed(() =>
	roundCurrency(Math.max(0, creditSaleRefundableExcess.value - normalizedCreditSaleCashRefund.value))
);
const creditSaleManagerRequired = computed(() =>
	Boolean(normalizedCreditSaleCashRefund.value > 0 && requireManagerPinCreditSaleCash.value)
);

const totalPaymentAmount = computed(() =>
	roundCurrency(
		refundPayments.value.reduce((sum, payment) => sum + (Number(payment.amount) || 0), 0)
	)
);

const maxRefundableAmount = computed(() => {
	if (!originalInvoice.value) return 0;
	if (!isPartiallyPaid.value && !isOriginalCreditSale.value) return returnTotal.value;

	const grandTotal = Math.abs(originalInvoice.value.grand_total) || 1;
	const returnRatio = returnTotal.value / grandTotal;
	return roundCurrency(Math.min(returnTotal.value, originalPaidAmount.value * returnRatio));
});

// Amount that goes toward credit balance (for partially paid invoices)
const creditAdjustmentAmount = computed(() =>
	isPartiallyPaid.value
		? roundCurrency(Math.max(0, returnTotal.value - maxRefundableAmount.value))
		: 0
);

// Summary display helpers for the Return Summary section
const showPartialBreakdown = computed(
	() => !isExchangeCreditMode.value && isPartiallyPaid.value && !isOriginalCreditSale.value
);
const summaryRefundLabel = computed(() => {
	if (isExchangeCreditMode.value) return "Exchange Credit:";
	if (isOriginalCreditSale.value) return "Return Value:";
	if (paymentHubManaged.value) return "Refund to Original Payment:";
	return showPartialBreakdown.value ? "Cash Refund:" : "Refund Amount:";
});
const summaryRefundAmount = computed(() =>
	isExchangeCreditMode.value
		? returnTotal.value
		: showPartialBreakdown.value
		? maxRefundableAmount.value
		: returnTotal.value
);

watch(summaryRefundAmount, () => {
	if (paymentHubManaged.value) applyPaymentHubRefundAmounts();
});

// Cache RTL direction check (only needs to run once per session)
const isRTL = document.documentElement.dir === "rtl";
const paymentSelectStyle = {
	backgroundPosition: isRTL ? "left 12px center" : "right 12px center",
};

const canCreateReturn = computed(() => {
	const hasSelectedItems = selectedItems.value.length > 0;
	if (!hasSelectedItems || !hasOpenShift.value) return false;
	if (isExchangeCreditMode.value) return true;
	if (paymentHubPlanLoading.value || paymentHubPlanError.value) return false;
	// Credit-sale returns reverse open A/R first. Cash is optional and limited to
	// the eligible excess; when selected, require a current-profile Cash mode and
	// (when configured) a Manager POS PIN. Any non-cash excess remains Customer Credit.
	if (isOriginalCreditSale.value) {
		if (!creditSaleCashRefundEnabled.value || normalizedCreditSaleCashRefund.value <= 0) return true;
		if (normalizedCreditSaleCashRefund.value > creditSaleRefundableExcess.value + 0.0005) return false;
		if (!creditSaleCashMode.value) return false;
		if (creditSaleManagerRequired.value && creditSaleManagerPin.value.trim().length < 4) return false;
		return true;
	}
	if (addToCustomerCredit.value) return true;

	const payments = refundPayments.value;
	if (paymentHubManaged.value) {
		const active = payments.filter((payment) => Number(payment.amount || 0) > 0);
		if (!active.length) return false;
		if (active.some((payment) => !payment.refund_supported && !payment.override_to_cash)) return false;
		if (
			active.some(
				(payment) =>
					Number(payment.amount || 0) > Number(payment.max_refundable || 0) + 0.0005
			)
		)
			return false;
		if (hasRefundOverride.value && !refundOverrideReason.value.trim()) return false;
		return Math.abs(totalPaymentAmount.value - summaryRefundAmount.value) < 0.01;
	}
	if (isPartiallyPaid.value) {
		if (!payments.length) return true;
		const hasValidPayments = payments.every(
			(payment) => payment.mode_of_payment && payment.amount >= 0
		);
		return (
			hasValidPayments &&
			Math.abs(totalPaymentAmount.value - maxRefundableAmount.value) < 0.01
		);
	}

	if (!payments.length) return false;
	const hasValidPayments = payments.every(
		(payment) => payment.mode_of_payment && payment.amount > 0
	);
	return hasValidPayments && Math.abs(totalPaymentAmount.value - returnTotal.value) < 0.01;
});

// Shared filter function to avoid duplicate code
const filterInvoicesByTerm = (invoices, searchTerm) => {
	if (!searchTerm) return invoices;
	const term = searchTerm.toLowerCase();
	return invoices.filter(
		(invoice) =>
			invoice.name.toLowerCase().includes(term) ||
			invoice.customer_name?.toLowerCase().includes(term) ||
			invoice.contact_mobile?.toLowerCase().includes(term)
	);
};

// Memoized search term to avoid recalculating in multiple computeds
const normalizedSearchTerm = computed(() => invoiceListFilter.value?.trim() || "");

const filteredInvoiceList = computed(() => {
	return filterInvoicesByTerm(invoiceList.value, normalizedSearchTerm.value);
});

// Autocomplete suggestions - reuses filtered list, just limits results
const searchSuggestions = computed(() => {
	if (normalizedSearchTerm.value.length < MIN_SEARCH_LENGTH) return [];
	return filteredInvoiceList.value.slice(0, MAX_SUGGESTIONS);
});

// Debounce timer for server search (will be cleaned up on unmount)
let serverSearchTimeout = null;

// Helper to check if search term looks like an invoice number
const looksLikeInvoiceNumber = (term) =>
	INVOICE_PATTERN.test(term) || INVOICE_FORMAT_PATTERN.test(term) || term.includes("-");

// Watch for search input changes and auto-search server when no local matches
watch(normalizedSearchTerm, (searchTerm) => {
	// Clear any pending search
	if (serverSearchTimeout) {
		clearTimeout(serverSearchTimeout);
		serverSearchTimeout = null;
	}

	// Early exit conditions
	if (!searchTerm || searchTerm.length < MIN_SERVER_SEARCH_LENGTH) return;
	if (!looksLikeInvoiceNumber(searchTerm)) return;

	// Check if we already have this in local results (reuse filtered list)
	if (filteredInvoiceList.value.length > 0) return;

	// Debounce server search
	serverSearchTimeout = setTimeout(() => {
		searchInvoiceByNumberResource.submit({
			search_term: searchTerm,
			pos_profile: props.posProfile,
		});
	}, SEARCH_DEBOUNCE_MS);
});

// Auto-populate payment amount when return total changes (single payment only)
watch(returnTotal, (newTotal) => {
	if (isExchangeCreditMode.value) return;
	if (!returnModal.visible || !showDialog.value || isOriginalCreditSale.value) return;
	if (paymentHubManaged.value) {
		applyPaymentHubRefundAmounts();
		return;
	}
	if (refundPayments.value.length !== 1 || newTotal <= 0) return;

	refundPayments.value[0].amount = isPartiallyPaid.value
		? roundCurrency(maxRefundableAmount.value)
		: newTotal;
});

// Methods
function extractErrorMessage(error, fallbackMessage = __("Failed to create return invoice")) {
	if (!error) return fallbackMessage;
	if (error.messages?.length) return error.messages.join(", ");

	if (error._server_messages) {
		try {
			const serverMessages = JSON.parse(error._server_messages);
			const firstMessage = serverMessages[0] && JSON.parse(serverMessages[0]);
			if (firstMessage?.message) return firstMessage.message;
		} catch (parseError) {
			// Ignore JSON parse errors, continue to other extraction methods
		}
	}

	if (typeof error.exc === "string") {
		const validationMatch = error.exc.match(/ValidationError: (.+?)\\n/);
		if (validationMatch) return validationMatch[1];
	}

	if (error.httpStatusText && error.httpStatusText !== "Expectation Failed")
		return error.httpStatusText;
	if (error.message && error.message !== "ValidationError") return error.message;
	return fallbackMessage;
}

function openErrorDialog(message, title = __("Validation Error")) {
	Object.assign(errorDialog, { visible: true, title, message });
}

function closeErrorDialog() {
	errorDialog.visible = false;
}

function focusReturnBarcodeInput() {
	nextTick(() => returnBarcodeInput.value?.focus());
}

function setReturnBarcodeStatus(type, message) {
	returnBarcodeStatus.type = type;
	returnBarcodeStatus.message = message;
	if (returnBarcodeStatusTimer) clearTimeout(returnBarcodeStatusTimer);
	returnBarcodeStatusTimer = setTimeout(() => {
		returnBarcodeStatus.type = "";
		returnBarcodeStatus.message = "";
	}, 2500);
}

function roundedReturnQty(value) {
	return Math.round((Number(value) || 0) * 1000000) / 1000000;
}

function handleReturnBarcodeScan() {
	const barcode = returnBarcode.value.trim();
	if (!barcode) {
		focusReturnBarcodeInput();
		return;
	}

	// Clear/refocus immediately. Hardware scanners can submit the next barcode while
	// the previous lookup is still running; QueuedMutex preserves scan order.
	returnBarcode.value = "";
	focusReturnBarcodeInput();

	returnBarcodeQueue.withLock(async () => {
		returnBarcodeBusy.value = true;
		try {
			const detail = await call("pos_next.api.items.search_by_barcode", {
				barcode,
				pos_profile: props.posProfile,
			});
			if (!detail?.item_code) throw new Error(__("Item not found"));

			let candidates = returnItems.value.filter((item) => item.item_code === detail.item_code);
			const scannedUom = detail.resolved_uom || detail.uom || detail.stock_uom;
			if (scannedUom) {
				const exactUom = candidates.filter(
					(item) => String(item.uom || item.stock_uom || "") === String(scannedUom)
				);
				if (exactUom.length) candidates = exactUom;
			}

			if (!candidates.length) {
				setReturnBarcodeStatus(
					"error",
					__("Barcode does not belong to this invoice: {0}", [barcode])
				);
				return;
			}

			const increment = Math.max(Number(detail.resolved_qty || 1), 0.001);
			const target = candidates.find((item) => {
				const current = item.selected ? Number(item.return_qty || 0) : 0;
				return current + 0.000001 < Number(item.quantity || 0);
			});

			if (!target) {
				setReturnBarcodeStatus(
					"error",
					__("All returnable quantity for {0} is already selected", [detail.item_code])
				);
				return;
			}

			const current = target.selected ? Number(target.return_qty || 0) : 0;
			const maximum = Number(target.quantity || 0);
			const nextQty = roundedReturnQty(current + increment);
			if (nextQty > maximum + 0.000001) {
				setReturnBarcodeStatus(
					"error",
					__("Cannot return more than {0} of {1}", [maximum, detail.item_code])
				);
				return;
			}

			target.selected = true;
			target.return_qty = nextQty;
			setReturnBarcodeStatus(
				"success",
				__("{0}: {1} / {2}", [detail.item_code, nextQty, maximum])
			);
		} catch (error) {
			console.error("Return barcode lookup failed:", error);
			setReturnBarcodeStatus(
				"error",
				extractErrorMessage(error, __("Barcode not found: {0}", [barcode]))
			);
		} finally {
			returnBarcodeBusy.value = false;
			focusReturnBarcodeInput();
		}
	});
}

function normalizeItemQuantity(item) {
	const maxQuantity = Number(item.quantity) || 0;
	const currentQuantity = Number(item.return_qty);
	const validQuantity = Number.isFinite(currentQuantity) ? currentQuantity : 1;
	item.return_qty = Math.max(1, Math.min(validQuantity, maxQuantity || validQuantity));
}

function validateSelectedItems() {
	const invalidItems = selectedItems.value.filter((item) => item.return_qty > item.quantity);
	if (!invalidItems.length) return true;

	invalidItems.forEach(normalizeItemQuantity);
	const errorDetails = invalidItems
		.map((item) => __("{0}: maximum {1}", [item.item_name || item.item_code, item.quantity]))
		.join("\n");
	const errorMessage = __("Adjust return quantities before submitting.\n\n{0}", [errorDetails]);
	submitError.value = errorMessage;
	openErrorDialog(errorMessage);
	return false;
}

function addPaymentRow() {
	if (paymentHubManaged.value) return;
	refundPayments.value.push({ mode_of_payment: "", amount: 0 });
}

function removePaymentRow(paymentIndex) {
	if (paymentHubManaged.value) return;
	refundPayments.value.splice(paymentIndex, 1);
}

function updateRefundPaymentAmount(payment, value) {
	let amount = Number.parseFloat(value) || 0;
	amount = Math.max(0, amount);
	if (paymentHubManaged.value) {
		amount = Math.min(amount, Number(payment.max_refundable || 0));
	}
	payment.amount = roundCurrency(amount);
}

function adjustRefundPayment(payment, delta) {
	updateRefundPaymentAmount(payment, (Number(payment.amount) || 0) + delta);
}

/**
 * Cross-branch return — frontend safety net (Layer 2).
 *
 * Pre-fills refund payment rows from the original invoice's payments.
 * The backend (prepare_return_invoice) already remaps foreign payment modes
 * by type (Cash→Cash, Bank→Bank) via _remap_foreign_payment_modes. This
 * function provides a second line of defense: if a mode in the original
 * invoice doesn't exist in the current POS profile's paymentMethods, it
 * falls back to the profile's default (first) mode.
 *
 * Timing:
 *   - Called from fetchInvoiceResource.onSuccess (may run before
 *     paymentMethods are loaded from the async profile fetch).
 *   - If paymentMethods is empty, we skip the remap and trust the
 *     backend's remapped values. loadPaymentMethodsResource.onSuccess
 *     will re-call this function once methods are available.
 *
 * The payment mode dropdown (<select>) only shows modes from the current
 * profile's paymentMethods. A foreign mode would appear as an unselectable
 * value, so this remap also ensures the dropdown works correctly.
 */
function initializePaymentsFromInvoice() {
	if (paymentHubManaged.value) {
		initializePaymentHubRefunds();
		return;
	}
	if (isOriginalCreditSale.value) {
		refundPayments.value = [];
		return;
	}

	const defaultMode = paymentMethods.value[0]?.mode_of_payment || "";

	const invoicePayments = originalInvoice.value?.payments;
	if (invoicePayments?.length) {
		// Only remap when paymentMethods are loaded. When null (not yet loaded),
		// the backend has already remapped via _remap_foreign_payment_modes,
		// so the modes are safe to use as-is.
		const currentModes = paymentMethods.value.length
			? new Set(paymentMethods.value.map((m) => m.mode_of_payment))
			: null;

		refundPayments.value = invoicePayments.map((payment) => ({
			mode_of_payment:
				currentModes && !currentModes.has(payment.mode_of_payment)
					? defaultMode
					: payment.mode_of_payment,
			amount: isPartiallyPaid.value ? 0 : Math.abs(payment.amount),
		}));
	} else {
		refundPayments.value = [
			{
				mode_of_payment: defaultMode,
				amount: 0,
			},
		];
	}
}

const paymentHubLegacyProtected = computed(() => Boolean(paymentHubPlan.value?.legacy_protected));
const paymentHubManaged = computed(() =>
	Boolean(paymentHubPlan.value?.managed || paymentHubPlan.value?.legacy_protected)
);
const hasRetryableFailedRefund = computed(() =>
	Boolean(
		paymentHubManaged.value &&
			returnRefundStatus.value?.rows?.some(
				(row) => row?.can_retry || row?.status === "Failed"
			)
	)
);

const hasRefundOverride = computed(() =>
	refundPayments.value.some(
		(payment) => payment.override_to_cash && Number(payment.amount || 0) > 0
	)
);
const requiresManagerAuthorization = computed(() =>
	refundPayments.value.some(
		(payment) =>
			Number(payment.amount || 0) > 0 &&
			(payment.authorization_required || payment.override_to_cash)
	)
);

function toggleRefundOverride(payment) {
	if (!payment.override_allowed) return;
	payment.override_to_cash = !payment.override_to_cash;
	if (payment.override_to_cash) {
		const target = payment.override_targets?.[0];
		payment.override_mode_of_payment = target?.mode_of_payment || "Cash";
	}
}

function effectiveRefundMode(payment) {
	return payment.override_to_cash ? payment.override_mode_of_payment : payment.mode_of_payment;
}

async function loadPaymentHubRefundPlan() {
	paymentHubPlan.value = null;
	paymentHubPlanLoading.value = true;
	paymentHubPlanError.value = "";
	returnDraftDoc.value = null;
	returnRefundStatus.value = null;
	if (!originalInvoice.value?.name) {
		paymentHubPlanLoading.value = false;
		return;
	}

	try {
		const result = await call("erpnext_payment_hub.pos.refund.get_refund_plan", {
			original_invoice: originalInvoice.value.name,
		});
		if (result?.managed || result?.legacy_protected) {
			paymentHubPlan.value = result;
			addToCustomerCredit.value = false;
			initializePaymentHubRefunds();
		}
	} catch (error) {
		console.error("Payment Hub refund plan check failed", error);
		paymentHubPlanError.value = extractErrorMessage(
			error,
			__("Unable to verify the original payment source. Return is blocked for safety.")
		);
	} finally {
		paymentHubPlanLoading.value = false;
	}
}

function initializePaymentHubRefunds() {
	if (!paymentHubPlan.value?.managed && !paymentHubPlan.value?.legacy_protected) return;
	refundPayments.value = (paymentHubPlan.value.sources || []).map((source) => ({
		mode_of_payment: source.mode_of_payment,
		amount: 0,
		source_allocation: source.source_allocation,
		channel: source.channel,
		provider_account: source.provider_account,
		provider: source.provider,
		actual_payment_method: source.actual_payment_method,
		gateway_transaction: source.gateway_transaction,
		max_refundable: Number(source.refundable_amount || 0),
		refund_supported: source.refund_supported !== false,
		authorization_required: source.authorization_required === true,
		override_allowed: source.override_allowed === true,
		override_targets: source.override_targets || [],
		override_to_cash: false,
		override_mode_of_payment: source.override_targets?.[0]?.mode_of_payment || "Cash",
		warning: source.warning || null,
	}));
	applyPaymentHubRefundAmounts();
}

function applyPaymentHubRefundAmounts() {
	if (!paymentHubManaged.value) return;
	let remaining = Number(summaryRefundAmount.value || 0);
	for (const payment of refundPayments.value) {
		const maxAmount = Number(payment.max_refundable || 0);
		payment.amount = roundCurrency(Math.min(maxAmount, Math.max(remaining, 0)));
		remaining = roundCurrency(Math.max(0, remaining - payment.amount));
	}
}

// Resource for checking invoice return validity (defined early for use in helpers)
const checkInvoiceValidityResource = createResource({
	url: "pos_next.api.invoices.check_invoice_return_validity",
	auto: false,
});

/**
 * Shared validity handler - processes validity response and shows appropriate UI
 * Returns true if invoice is valid, false otherwise
 */
function handleValidityResponse(validity) {
	if (validity.valid) return true;

	if (validity.error_type === "return_period_expired") {
		Object.assign(returnExpiredDialog, {
			invoiceName: validity.invoice_name,
			invoiceDate: validity.invoice_date,
			daysSince: validity.days_since,
			allowedDays: validity.allowed_days,
			visible: true,
		});
	} else if (validity.error_type === "not_found") {
		showError(validity.message || __("Invoice not found"));
	} else {
		showError(validity.message || __("Cannot process return for this invoice"));
	}
	return false;
}

/**
 * Opens return modal after fetching invoice details
 */
function openReturnModal(invoice) {
	submitError.value = "";
	fetchInvoiceResource.fetch({
		invoice_name: invoice.name,
		pos_opening_shift: props.posOpeningShift,
	});
	returnModal.visible = true;
}

/**
 * Check validity and open return modal if valid
 * @param {string} invoiceName - Invoice name to check
 * @param {boolean} fallbackOnError - If true, opens modal directly on validity check error
 */
async function checkValidityAndOpenModal(invoiceName, fallbackOnError = false) {
	try {
		const validity = await checkInvoiceValidityResource.fetch({
			invoice_name: invoiceName,
		});
		if (handleValidityResponse(validity)) {
			fetchInvoiceResource.fetch({
				invoice_name: invoiceName,
				pos_opening_shift: props.posOpeningShift,
			});
			returnModal.visible = true;
		}
	} catch (error) {
		console.error("Error checking invoice validity:", error);
		if (fallbackOnError) {
			// Fallback to direct open if validity check fails
			openReturnModal({ name: invoiceName });
		} else {
			showError(__("Failed to check invoice"));
		}
	}
}

/**
 * Search for an invoice directly by invoice number.
 */
async function searchInvoiceDirectly() {
	const searchTerm = normalizedSearchTerm.value;
	if (!searchTerm || !looksLikeInvoiceNumber(searchTerm)) return;
	await checkValidityAndOpenModal(searchTerm, false);
}

function closeReturnModal() {
	returnModal.visible = false;
	resetForm();
	// Notify parent that the return dialog is closed
	emit("update:modelValue", false);
}

function selectAllFilteredItems() {
	filteredReturnItems.value.forEach((item) => {
		item.selected = true;
		item.return_qty = item.quantity;
	});
}

function deselectAllItems() {
	returnItems.value.forEach((item) => {
		item.selected = false;
	});
}

function toggleItemSelection(item) {
	item.selected = !item.selected;
	if (item.selected && item.return_qty === 0) {
		item.return_qty = item.quantity;
	}
}

function handleKeyboardShortcuts(event) {
	if (!returnModal.visible) return;

	const isModifierPressed = event.ctrlKey || event.metaKey;

	// Ctrl/Cmd+A selects all filtered items (respects search filter)
	if (isModifierPressed && event.key === "a") {
		event.preventDefault();
		selectAllFilteredItems();
	}
	if (
		isModifierPressed &&
		event.key === "Enter" &&
		canCreateReturn.value &&
		!isSubmitting.value
	) {
		event.preventDefault();
		handleCreateReturn();
	}
	if (event.key === "Escape") closeReturnModal();
}

function incrementReturnQuantity(item) {
	if (item.return_qty < item.quantity) {
		item.return_qty++;
	}
}

function decrementReturnQuantity(item) {
	if (item.return_qty > 1) {
		item.return_qty--;
	}
}

function buildPaymentHubReturnInvoiceData() {
	const baseDoc = preparedReturnDoc.value || {};
	const invoiceData = {
		doctype: "Sales Invoice",
		pos_profile: props.posProfile,
		posa_pos_opening_shift: props.posOpeningShift,
		customer: baseDoc.customer || originalInvoice.value.customer,
		company: baseDoc.company || originalInvoice.value.company,
		is_return: 1,
		return_against: baseDoc.return_against || originalInvoice.value.name,
		update_outstanding_for_self: 0,
		is_pos: 1,
		update_stock: 1,
		sales_team:
			baseDoc.sales_team?.map((member) => ({
				sales_person: member.sales_person,
				allocated_percentage: member.allocated_percentage || 0,
			})) || [],
		items: selectedItems.value.map((item) => ({
			item_code: item.item_code,
			item_name: item.item_name,
			qty: -Math.abs(item.return_qty),
			rate: item.rate,
			warehouse: item.warehouse,
			uom: item.uom,
			conversion_factor: item.conversion_factor || 1,
			sales_invoice_item: item.name,
		})),
		add_to_customer_balance: false,
		payments: refundPayments.value
			.filter((payment) => Number(payment.amount || 0) > 0)
			.map((payment) => ({
				mode_of_payment: effectiveRefundMode(payment),
				amount: -Math.abs(payment.amount),
			})),
		remarks: returnReason.value || __("Return against {0}", [originalInvoice.value.name]),
	};
	if (returnDraftDoc.value?.name) invoiceData.name = returnDraftDoc.value.name;
	return invoiceData;
}

function finishReturnSuccess(data) {
	submitError.value = "";
	const successPayload = {
		...data,
		customer: originalInvoice.value?.customer,
		customer_name: originalInvoice.value?.customer_name,
		exchange_credit: isExchangeCreditMode.value,
	};
	closeReturnModal();
	emit("return-created", successPayload);
	loadInvoicesResource.reload();
	showSuccess(__("Return invoice {0} created successfully", [data.name]));
}

async function submitPaymentHubReturnDraft() {
	if (!returnDraftDoc.value?.name) throw new Error(__("Return draft is missing"));
	const result = await call("pos_next.api.invoices.submit_invoice", {
		invoice: JSON.stringify(returnDraftDoc.value),
		data: JSON.stringify({}),
	});
	finishReturnSuccess(result);
	return result;
}

function cancelRefundAuthorization() {
	refundAuthDialog.visible = false;
	refundAuthDialog.loading = false;
	refundAuthDialog.password = "";
	refundAuthDialog.error = "";
	const resolve = refundAuthResolve;
	refundAuthResolve = null;
	resolve?.(null);
}

async function submitRefundAuthorization() {
	if (refundAuthDialog.loading) return;
	if (!refundAuthDialog.approver || !refundAuthDialog.password || !refundAuthDialog.reason.trim()) {
		refundAuthDialog.error = __("Manager username, password and reason are required");
		return;
	}
	refundAuthDialog.loading = true;
	refundAuthDialog.error = "";
	try {
		const overridePayment = refundAuthDialog.refundLines.find((line) => line.override_channel);
		const result = await call("erpnext_payment_hub.pos.authorization.authorize_pos_refund", {
			approver: refundAuthDialog.approver,
			password: refundAuthDialog.password,
			original_invoice: originalInvoice.value.name,
			return_invoice: refundAuthDialog.returnInvoice,
			amount: roundCurrency(
				refundAuthDialog.refundLines.reduce(
					(sum, line) => sum + Number(line.amount || 0),
					0
				)
			),
			reason: refundAuthDialog.reason.trim(),
			source_allocations: JSON.stringify(
				refundAuthDialog.refundLines.map((line) => line.source_allocation)
			),
			is_override: hasRefundOverride.value ? 1 : 0,
			override_channel: overridePayment?.override_channel || null,
			override_mode_of_payment: overridePayment?.override_mode_of_payment || null,
		});
		refundAuthDialog.visible = false;
		refundAuthDialog.password = "";
		const resolve = refundAuthResolve;
		refundAuthResolve = null;
		resolve?.(result?.authorization_token || null);
	} catch (error) {
		refundAuthDialog.password = "";
		refundAuthDialog.error = extractErrorMessage(error, __("Authorization failed"));
	} finally {
		refundAuthDialog.loading = false;
	}
}

function requestRefundAuthorization(returnInvoice, refundLines) {
	if (!requiresManagerAuthorization.value) return Promise.resolve(null);
	refundAuthDialog.returnInvoice = returnInvoice;
	refundAuthDialog.refundLines = refundLines;
	refundAuthDialog.password = "";
	refundAuthDialog.error = "";
	refundAuthDialog.reason =
		refundOverrideReason.value.trim() ||
		returnReason.value.trim() ||
		__("POS customer return");
	refundAuthDialog.visible = true;
	return new Promise((resolve) => {
		refundAuthResolve = resolve;
	});
}

watch(
	() => refundAuthDialog.visible,
	(visible) => {
		if (!visible && refundAuthResolve && !refundAuthDialog.loading) {
			const resolve = refundAuthResolve;
			refundAuthResolve = null;
			refundAuthDialog.password = "";
			resolve(null);
		}
	}
);

async function handleLegacyProtectedReturn() {
	if (!hasRefundOverride.value) {
		throw new Error(
			__("This legacy Electronic / Physical payment requires a manager-authorized Cash override.")
		);
	}

	const invoiceData = buildPaymentHubReturnInvoiceData();
	const draft = await call("pos_next.api.invoices.update_invoice", {
		data: JSON.stringify(invoiceData),
	});
	returnDraftDoc.value = draft;

	const refundLines = refundPayments.value
		.filter((payment) => Number(payment.amount || 0) > 0)
		.map((payment) => ({
			source_allocation: payment.source_allocation,
			amount: roundCurrency(payment.amount),
			override_channel: "Cash",
			override_mode_of_payment: payment.override_mode_of_payment || "Cash",
			override_reason: refundOverrideReason.value.trim(),
		}));

	const authorizationToken = await requestRefundAuthorization(draft.name, refundLines);
	if (!authorizationToken) {
		showWarning(__("Return was not submitted. Manager Refund Override authorization is required."));
		return { authorization_required: true, return_invoice: draft.name };
	}

	return await submitPaymentHubReturnDraft();
}

async function handlePaymentHubReturn() {
	if (paymentHubLegacyProtected.value) {
		return await handleLegacyProtectedReturn();
	}

	const invoiceData = buildPaymentHubReturnInvoiceData();
	const draft = await call("pos_next.api.invoices.update_invoice", {
		data: JSON.stringify(invoiceData),
	});
	returnDraftDoc.value = draft;

	const refundLines = refundPayments.value
		.filter((payment) => Number(payment.amount || 0) > 0)
		.map((payment) => ({
			source_allocation: payment.source_allocation,
			amount: roundCurrency(payment.amount),
			override_channel: payment.override_to_cash ? "Cash" : null,
			override_mode_of_payment: payment.override_to_cash
				? payment.override_mode_of_payment
				: null,
			override_reason: payment.override_to_cash ? refundOverrideReason.value.trim() : null,
		}));

	let authorizationToken = null;
	if (requiresManagerAuthorization.value) {
		authorizationToken = await requestRefundAuthorization(draft.name, refundLines);
		if (!authorizationToken) {
			showWarning(__("Refund was not sent. Manager authorization is required."));
			return { authorization_required: true, return_invoice: draft.name };
		}
	}

	const status = await call("erpnext_payment_hub.pos.refund.process_pos_return_refund", {
		original_invoice: originalInvoice.value.name,
		return_invoice: draft.name,
		refund_lines: JSON.stringify(refundLines),
		reason: returnReason.value || "POS customer return",
		authorization_token: authorizationToken,
	});
	returnRefundStatus.value = status;

	if (status?.all_complete) {
		return await submitPaymentHubReturnDraft();
	}

	if (status?.needs_review) {
		if (status?.rows?.some((row) => row?.can_retry || row?.status === "Failed")) {
			showWarning(
				__(
					"Refund failed with the provider. Return invoice {0} remains Draft. Click Retry Refund to create a new provider refund attempt.",
					[draft.name]
				)
			);
			return status;
		}
		throw new Error(
			__(
				"Refund requires manual review. Return invoice {0} remains Draft.",
				[draft.name]
			)
		);
	}

	showWarning(
		__(
			"Refund is pending with the payment provider. Return invoice {0} remains Draft. Use Check Refund to continue after confirmation.",
			[draft.name]
		)
	);
	return status;
}

async function handleCheckRefund() {
	if (!returnDraftDoc.value?.name || isSubmitting.value) return;
	isSubmitting.value = true;
	try {
		const status = await call("erpnext_payment_hub.pos.refund.refresh_return_refunds", {
			return_invoice: returnDraftDoc.value.name,
		});
		returnRefundStatus.value = status;
		if (status?.all_complete) {
			await submitPaymentHubReturnDraft();
		} else if (status?.needs_review) {
			if (status?.rows?.some((row) => row?.can_retry || row?.status === "Failed")) {
				showWarning(__("Refund failed with the provider. Click Retry Refund to try again."));
			} else {
				openErrorDialog(
					__("Refund requires manual review before the return can be submitted."),
					__("Refund Review Required")
				);
			}
		} else {
			showWarning(__("Refund is still pending with the payment provider."));
		}
	} catch (error) {
		const errorMsg = extractErrorMessage(error);
		submitError.value = errorMsg;
		openErrorDialog(errorMsg);
	} finally {
		isSubmitting.value = false;
	}
}

async function handleCreateReturn() {
	if (!canCreateReturn.value || isSubmitting.value) return;
	if (!hasOpenShift.value) {
		const message = __("Open a shift before creating a return invoice.");
		submitError.value = message;
		openErrorDialog(message);
		return;
	}

	if (!validateSelectedItems()) {
		return;
	}

	submitError.value = "";
	isSubmitting.value = true;

	try {
		if (!isExchangeCreditMode.value && paymentHubManaged.value) {
			await handlePaymentHubReturn();
			return;
		}

		const result = await createReturnResource.submit();

		// Check if result contains an error (HTTP 417 might return error in response body)
		if (result && result.exc) {
			throw result;
		}
	} catch (error) {
		console.error("Caught error in handleCreateReturn:", error);
		if (!submitError.value) {
			const errorMsg = extractErrorMessage(error);
			submitError.value = errorMsg;
			openErrorDialog(errorMsg);
		}
	} finally {
		isSubmitting.value = false;
	}
}

watch(creditSaleCashRefundEnabled, (enabled) => {
	if (enabled) {
		creditSaleCashRefundAmount.value = creditSaleRefundableExcess.value;
		if (!creditSaleCashMode.value && creditSaleCashModes.value.length) {
			creditSaleCashMode.value = creditSaleCashModes.value[0];
		}
	} else {
		creditSaleCashRefundAmount.value = 0;
		creditSaleManagerPin.value = "";
	}
});

watch(creditSaleRefundableExcess, (maxAmount) => {
	if (creditSaleCashRefundEnabled.value && Number(creditSaleCashRefundAmount.value || 0) > maxAmount) {
		creditSaleCashRefundAmount.value = maxAmount;
	}
});

function resetForm() {
	// Reset invoice and return document state
	originalInvoice.value = null;
	preparedReturnDoc.value = null;
	returnItems.value = [];
	returnBarcode.value = "";
	returnBarcodeBusy.value = false;
	returnBarcodeStatus.message = "";
	returnBarcodeStatus.type = "";
	returnReason.value = "";
	refundPayments.value = [];
	addToCustomerCredit.value = false;
	paymentHubPlan.value = null;
	paymentHubPlanLoading.value = false;
	paymentHubPlanError.value = "";
	returnDraftDoc.value = null;
	returnRefundStatus.value = null;
	refundOverrideReason.value = "";
	refundAuthDialog.visible = false;
	refundAuthDialog.loading = false;
	refundAuthDialog.approver = "";
	refundAuthDialog.password = "";
	refundAuthDialog.reason = "";
	refundAuthDialog.error = "";
	refundAuthDialog.returnInvoice = null;
	refundAuthDialog.refundLines = [];
	refundAuthResolve = null;

	// Reset list and search state
	invoiceList.value = [];
	invoiceListFilter.value = "";
	itemSearchFilter.value = "";

	// Reset submission state
	submitError.value = "";
	isSubmitting.value = false;

	// Reset modal/dialog state
	returnModal.visible = false;
	errorDialog.visible = false;
	errorDialog.message = "";

	// Reset payment tracking state
	isOriginalCreditSale.value = false;
	isPartiallyPaid.value = false;
	originalPaidAmount.value = 0;
	originalOutstandingAmount.value = 0;
	creditSaleCashRefundEnabled.value = false;
	creditSaleCashRefundAmount.value = 0;
	creditSaleCashMode.value = creditSaleCashModes.value[0] || "";
	creditSaleManagerPin.value = "";

	// Reset customer credit option
	addToCustomerCredit.value = false;
}

// Date formatter instance (reused for performance)
const dateFormatter = new Intl.DateTimeFormat(DEFAULT_LOCALE, DATE_FORMAT_OPTIONS);

function formatDate(dateStr) {
	if (!dateStr) return "";
	return dateFormatter.format(new Date(dateStr));
}

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency);
}

// Autocomplete handler functions
function onSearchInput() {
	showSuggestions.value = true;
	selectedSuggestionIndex.value = -1;
}

function showSuggestionsOnFocus() {
	if (normalizedSearchTerm.value.length >= MIN_SEARCH_LENGTH) {
		showSuggestions.value = true;
	}
}

function onSearchBlur() {
	// Delay to allow click on suggestion to register
	setTimeout(() => {
		showSuggestions.value = false;
		selectedSuggestionIndex.value = -1;
	}, 200);
}

function navigateSuggestion(direction) {
	if (!showSuggestions.value || searchSuggestions.value.length === 0) return;

	const maxIndex = searchSuggestions.value.length - 1;
	let newIndex = selectedSuggestionIndex.value + direction;

	if (newIndex < -1) newIndex = maxIndex;
	if (newIndex > maxIndex) newIndex = -1;

	selectedSuggestionIndex.value = newIndex;
}

function selectSuggestionOrSearch() {
	if (
		selectedSuggestionIndex.value >= 0 &&
		selectedSuggestionIndex.value < searchSuggestions.value.length
	) {
		// Select the highlighted suggestion
		selectSuggestion(searchSuggestions.value[selectedSuggestionIndex.value]);
	} else if (invoiceListFilter.value?.trim()) {
		// No suggestion selected, try direct search
		closeSuggestions();
		searchInvoiceDirectly();
	}
}

async function selectSuggestion(invoice) {
	closeSuggestions();
	invoiceListFilter.value = invoice.name;
	// Check validity first, with fallback to direct open on error
	await checkValidityAndOpenModal(invoice.name, true);
}

function closeSuggestions() {
	showSuggestions.value = false;
	selectedSuggestionIndex.value = -1;
}

function clearSearch() {
	invoiceListFilter.value = "";
	closeSuggestions();
	invoiceSearchInput.value?.focus();
}

// ============================================
// UX Enhancement Helper Functions
// ============================================

/**
 * Escape special regex characters in a string
 */
function escapeRegex(str) {
	return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Highlight search matches in text with yellow background
 */
function highlightSearchMatch(text, searchTerm) {
	if (!text || !searchTerm) return text;
	const escaped = escapeRegex(searchTerm.trim());
	if (!escaped) return text;
	const regex = new RegExp(`(${escaped})`, "gi");
	return text.replace(regex, '<mark class="search-highlight">$1</mark>');
}
</script>

<style scoped>
/* Custom scrollbar for items list */
.overflow-y-auto::-webkit-scrollbar {
	width: 8px;
}

.overflow-y-auto::-webkit-scrollbar-track {
	background: #f1f1f1;
	border-radius: 4px;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
	background: #cbd5e1;
	border-radius: 4px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
	background: #94a3b8;
}

/* Smooth transitions */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
	opacity: 1;
}

/* Payment select dropdown - arrow icon via background-image, position handled by inline style */
.payment-select {
	background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%236B7280'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
	background-repeat: no-repeat;
	background-size: 20px;
}

/* Skeleton loading animation */
.skeleton-pulse {
	animation: skeleton-pulse 1.5s ease-in-out infinite;
}

@keyframes skeleton-pulse {
	0%,
	100% {
		opacity: 1;
	}
	50% {
		opacity: 0.4;
	}
}

.skeleton-card {
	animation: skeleton-fade-in 0.3s ease-out;
}

@keyframes skeleton-fade-in {
	from {
		opacity: 0;
		transform: translateY(4px);
	}
	to {
		opacity: 1;
		transform: translateY(0);
	}
}

/* Search highlight styling */
:deep(.search-highlight) {
	background-color: #fef08a;
	padding: 0 2px;
	border-radius: 2px;
	font-weight: 600;
}
</style>
