import { call } from "@/utils/apiWrapper"

class UomPolicyAdapter {
	constructor() {
		this.policyCache = new Map()
		this.pendingPolicyRequests = new Map()
		this.debug = false
		this.mode = "selling"

		this.methods = {
			getPolicyMap:
				"pos_branch_helper.uom_policy.pos_api.get_pos_uom_policy_map",
			getSinglePolicy:
				"pos_branch_helper.uom_policy.pos_api.get_pos_item_policy",
			checkAllowed:
				"pos_branch_helper.uom_policy.pos_api.check_pos_uom_allowed",
			validateBarcode:
				"pos_branch_helper.uom_policy.pos_api.validate_pos_barcode_uom",
		}
	}

	log(...args) {
		if (this.debug) {
			console.log("[UOM POLICY ADAPTER]", ...args)
		}
	}

	normalize(value) {
		return String(value || "").trim()
	}

	normalizeKey(value) {
		return this.normalize(value).toLowerCase()
	}

	isNonEmpty(value) {
		return this.normalize(value).length > 0
	}

	getItemCode(itemOrCode) {
		if (!itemOrCode) return ""
		if (typeof itemOrCode === "string") return this.normalize(itemOrCode)

		return this.normalize(
			itemOrCode.item_code ||
				itemOrCode.code ||
				itemOrCode.name ||
				itemOrCode.item ||
				"",
		)
	}

	getStockUom(item) {
		if (!item) return ""
		return this.normalize(item.stock_uom || item.uom || "")
	}

	makeSafeArray(value) {
		return Array.isArray(value) ? value : []
	}

	dedupeStrings(values = []) {
		const out = []
		const seen = new Set()

		for (const value of values) {
			const text = this.normalize(value)
			const key = this.normalizeKey(text)

			if (!text || seen.has(key)) continue
			seen.add(key)
			out.push(text)
		}

		return out
	}

	dedupeUomRows(rows = []) {
		const out = []
		const seen = new Set()

		for (const row of this.makeSafeArray(rows)) {
			const uom = this.normalize(row?.uom || row?.value || row?.label || "")
			const key = this.normalizeKey(uom)

			if (!uom || seen.has(key)) continue
			seen.add(key)

			out.push({
				...row,
				uom,
				conversion_factor: Number(row?.conversion_factor || 1) || 1,
				is_stock_uom: row?.is_stock_uom ? 1 : 0,
			})
		}

		return out
	}

	normalizePolicy(policy = {}, fallbackItem = null) {
		const itemCode =
			this.getItemCode(policy.item_code) || this.getItemCode(fallbackItem)
		const stockUom =
			this.normalize(policy.stock_uom) || this.getStockUom(fallbackItem)

		const allowedRows = this.dedupeUomRows(policy.allowed_rows || [])
		let allowedUoms = this.dedupeStrings(policy.allowed_uoms || [])

		if (!allowedUoms.length && allowedRows.length) {
			allowedUoms = this.dedupeStrings(allowedRows.map((row) => row.uom))
		}

		if (!allowedUoms.length && stockUom) {
			allowedUoms = [stockUom]
		}

		const allowedSet = new Set(allowedUoms.map((uom) => this.normalizeKey(uom)))

		let barcodeUoms = this.dedupeStrings(policy.barcode_uoms || [])
		if (barcodeUoms.length) {
			barcodeUoms = barcodeUoms.filter((uom) =>
				allowedSet.has(this.normalizeKey(uom)),
			)
		}

		const defaultUom = this.normalize(policy.default_uom)
		const safeDefaultUom =
			(defaultUom &&
				allowedSet.has(this.normalizeKey(defaultUom)) &&
				defaultUom) ||
			allowedUoms[0] ||
			stockUom

		return {
			item_code: itemCode,
			mode: this.normalize(policy.mode || this.mode || "selling").toLowerCase(),
			stock_uom: stockUom,
			default_uom: safeDefaultUom,
			allowed_uoms: allowedUoms,
			barcode_uoms: barcodeUoms,
			allowed_rows: allowedRows,
			all_rows: this.makeSafeArray(policy.all_rows),
		}
	}

	cachePolicy(itemCode, policy, fallbackItem = null) {
		const key = this.getItemCode(itemCode || fallbackItem)
		if (!key) return null

		const normalized = this.normalizePolicy(policy, fallbackItem)
		this.policyCache.set(key, normalized)
		return normalized
	}

	getPolicy(itemOrCode) {
		const itemCode = this.getItemCode(itemOrCode)
		if (!itemCode) return null
		return this.policyCache.get(itemCode) || null
	}

	hasPolicy(itemOrCode) {
		return !!this.getPolicy(itemOrCode)
	}

	clearCache(itemCode = null) {
		if (itemCode) {
			this.policyCache.delete(this.getItemCode(itemCode))
			return
		}

		this.policyCache.clear()
		this.pendingPolicyRequests.clear()
	}

	async ensurePolicyLoaded(itemOrCode, options = {}) {
		const itemCode = this.getItemCode(itemOrCode)
		if (!itemCode) return null

		if (!options.force && this.policyCache.has(itemCode)) {
			return this.policyCache.get(itemCode)
		}

		if (!options.force && this.pendingPolicyRequests.has(itemCode)) {
			return this.pendingPolicyRequests.get(itemCode)
		}

		const request = (async () => {
			try {
				const response = await call(this.methods.getSinglePolicy, {
					item_code: itemCode,
					mode: options.mode || this.mode,
				})

				const payload = response?.message || response || {}
				const policy = payload?.policy || null

				if (!policy) {
					return null
				}

				return this.cachePolicy(itemCode, policy, itemOrCode)
			} finally {
				this.pendingPolicyRequests.delete(itemCode)
			}
		})()

		this.pendingPolicyRequests.set(itemCode, request)
		return request
	}

	async ensurePoliciesLoaded(itemsOrCodes = [], options = {}) {
		const rawList = Array.isArray(itemsOrCodes) ? itemsOrCodes : [itemsOrCodes]
		const itemMap = new Map()

		for (const entry of rawList) {
			const itemCode = this.getItemCode(entry)
			if (!itemCode) continue
			if (!itemMap.has(itemCode)) {
				itemMap.set(itemCode, entry)
			}
		}

		const itemCodes = Array.from(itemMap.keys())
		if (!itemCodes.length) return {}

		const missing = itemCodes.filter(
			(itemCode) => options.force || !this.policyCache.has(itemCode),
		)

		if (!missing.length) {
			return this.getPolicyMap(itemCodes)
		}

		const requestKey = [...missing].sort().join("|")

		if (this.pendingPolicyRequests.has(requestKey)) {
			await this.pendingPolicyRequests.get(requestKey)
			return this.getPolicyMap(itemCodes)
		}

		const request = (async () => {
			try {
				const response = await call(this.methods.getPolicyMap, {
					item_codes: missing,
					mode: options.mode || this.mode,
				})

				const payload = response?.message || response || {}
				const policyMap = payload?.policy_map || {}

				for (const itemCode of Object.keys(policyMap)) {
					this.cachePolicy(itemCode, policyMap[itemCode], itemMap.get(itemCode))
				}
			} finally {
				this.pendingPolicyRequests.delete(requestKey)
			}
		})()

		this.pendingPolicyRequests.set(requestKey, request)
		await request

		for (const itemCode of missing) {
			if (!this.policyCache.has(itemCode)) {
				await this.ensurePolicyLoaded(itemMap.get(itemCode), options)
			}
		}

		return this.getPolicyMap(itemCodes)
	}

	getPolicyMap(itemsOrCodes = []) {
		const list = Array.isArray(itemsOrCodes) ? itemsOrCodes : [itemsOrCodes]
		const out = {}

		for (const entry of list) {
			const itemCode = this.getItemCode(entry)
			if (!itemCode) continue
			const policy = this.getPolicy(itemCode)
			if (policy) out[itemCode] = policy
		}

		return out
	}

	getAllowedUoms(itemOrCode) {
		const policy = this.getPolicy(itemOrCode)
		if (policy?.allowed_uoms?.length) {
			return [...policy.allowed_uoms]
		}

		const stockUom =
			typeof itemOrCode === "object" ? this.getStockUom(itemOrCode) : ""
		return stockUom ? [stockUom] : []
	}

	getAllowedUomRows(itemOrCode) {
		const policy = this.getPolicy(itemOrCode)
		if (policy?.allowed_rows?.length) {
			return policy.allowed_rows.map((row) => ({ ...row }))
		}

		const stockUom =
			typeof itemOrCode === "object" ? this.getStockUom(itemOrCode) : ""

		return stockUom
			? [
					{
						uom: stockUom,
						conversion_factor: 1,
						is_stock_uom: 1,
					},
				]
			: []
	}

	getDefaultUom(itemOrCode) {
		const policy = this.getPolicy(itemOrCode)
		if (policy?.default_uom) return policy.default_uom

		if (typeof itemOrCode === "object") {
			return this.getStockUom(itemOrCode)
		}

		return ""
	}

	isUomAllowed(itemOrCode, uom) {
		const target = this.normalizeKey(uom)
		if (!target) return false

		const allowedUoms = this.getAllowedUoms(itemOrCode)
		if (!allowedUoms.length) return false

		return allowedUoms.some((value) => this.normalizeKey(value) === target)
	}

	isBarcodeUomAllowed(itemOrCode, uom) {
		const target = this.normalizeKey(uom)
		if (!target) return false

		const policy = this.getPolicy(itemOrCode)
		if (!policy) {
			return this.isUomAllowed(itemOrCode, uom)
		}

		const barcodeUoms = this.makeSafeArray(policy.barcode_uoms)
		if (!barcodeUoms.length) {
			return this.isUomAllowed(itemOrCode, uom)
		}

		return barcodeUoms.some((value) => this.normalizeKey(value) === target)
	}

	isUomLocked(itemOrCode) {
		return this.getAllowedUoms(itemOrCode).length <= 1
	}

	getUomRow(itemOrCode, uom) {
		const target = this.normalizeKey(uom)

		const policyRows = this.getAllowedUomRows(itemOrCode)
		let match = policyRows.find((row) => this.normalizeKey(row.uom) === target)
		if (match) return { ...match }

		if (typeof itemOrCode === "object") {
			const itemUoms = this.makeSafeArray(itemOrCode.item_uoms)
			match = itemUoms.find((row) => this.normalizeKey(row?.uom) === target)
			if (match) {
				return {
					...match,
					uom: this.normalize(match.uom),
					conversion_factor: Number(match.conversion_factor || 1) || 1,
					is_stock_uom: 0,
				}
			}

			if (this.normalizeKey(this.getStockUom(itemOrCode)) === target) {
				return {
					uom: this.getStockUom(itemOrCode),
					conversion_factor: 1,
					is_stock_uom: 1,
				}
			}
		}

		return null
	}

	filterAllowedItemUoms(item) {
		if (!item) return []

		const allowed = this.getAllowedUoms(item)
		if (!allowed.length) return []

		const allowedSet = new Set(allowed.map((uom) => this.normalizeKey(uom)))
		const itemUoms = this.makeSafeArray(item.item_uoms)

		return this.dedupeUomRows(
			itemUoms.filter((row) => {
				const uom = this.normalize(row?.uom)
				if (!uom) return false
				if (this.normalizeKey(uom) === this.normalizeKey(item.stock_uom)) {
					return false
				}
				return allowedSet.has(this.normalizeKey(uom))
			}),
		)
	}

	buildSelectableUoms(item) {
		if (!item) return []

		const stockUom = this.getStockUom(item)
		const out = []
		const seen = new Set()

		const push = (uom, conversionFactor = 1, isStock = 0) => {
			const value = this.normalize(uom)
			const key = this.normalizeKey(value)

			if (!value || seen.has(key)) return
			seen.add(key)

			out.push({
				uom: value,
				label: value,
				value,
				conversion_factor: Number(conversionFactor || 1) || 1,
				is_stock_uom: isStock ? 1 : 0,
			})
		}

		const policyRows = this.getAllowedUomRows(item)
		if (policyRows.length) {
			for (const row of policyRows) {
				push(
					row.uom,
					row.conversion_factor || 1,
					row.is_stock_uom ||
						this.normalizeKey(row.uom) === this.normalizeKey(stockUom),
				)
			}
			return out
		}

		push(stockUom, 1, 1)

		for (const row of this.filterAllowedItemUoms(item)) {
			push(row.uom, row.conversion_factor || 1, 0)
		}

		return out
	}

	normalizeItem(item) {
		if (!item) return item

		const normalized = { ...item }
		const stockUom = this.getStockUom(normalized)

		normalized.stock_uom = stockUom
		normalized.item_uoms = this.dedupeUomRows(this.makeSafeArray(normalized.item_uoms))

		const filteredItemUoms = this.filterAllowedItemUoms(normalized)
		normalized.item_uoms = filteredItemUoms

		const safeDefaultUom = this.getDefaultUom(normalized) || stockUom
		if (!this.isUomAllowed(normalized, normalized.uom)) {
			normalized.uom = safeDefaultUom
		} else {
			normalized.uom = this.normalize(normalized.uom || safeDefaultUom)
		}

		const currentRow = this.getUomRow(normalized, normalized.uom)
		normalized.conversion_factor =
			Number(
				currentRow?.conversion_factor ||
					normalized.conversion_factor ||
					(normalized.uom === stockUom ? 1 : 1),
			) || 1

		normalized._allowed_uoms = this.getAllowedUoms(normalized)
		normalized._uom_locked = this.isUomLocked(normalized)
		normalized._default_uom = safeDefaultUom

		return normalized
	}

	async normalizeItemAsync(item, options = {}) {
		if (!item) return item
		await this.ensurePolicyLoaded(item, options)
		return this.normalizeItem(item)
	}

	applySafeDefaultUom(item) {
		if (!item) return item

		const safeUom = this.getDefaultUom(item) || this.getStockUom(item)
		const normalized = { ...item }

		normalized.uom = safeUom

		const row = this.getUomRow(normalized, safeUom)
		normalized.conversion_factor =
			Number(row?.conversion_factor || normalized.conversion_factor || 1) || 1

		return this.normalizeItem(normalized)
	}

	applySelectedUom(item, selectedUom) {
		if (!item) {
			return {
				ok: false,
				reason: "missing_item",
				item: item || null,
			}
		}

		if (!this.isUomAllowed(item, selectedUom)) {
			const fallbackItem = this.applySafeDefaultUom(item)
			return {
				ok: false,
				reason: "uom_not_allowed",
				item: fallbackItem,
				selected_uom: this.normalize(selectedUom),
				safe_uom: fallbackItem?.uom || this.getDefaultUom(item),
			}
		}

		const normalized = { ...item, uom: this.normalize(selectedUom) }
		const row = this.getUomRow(normalized, normalized.uom)

		if (row) {
			normalized.conversion_factor =
				Number(row.conversion_factor || normalized.conversion_factor || 1) || 1
		}

		return {
			ok: true,
			reason: null,
			item: this.normalizeItem(normalized),
			selected_uom: normalized.uom,
		}
	}

	async checkAllowed(itemOrCode, uom, options = {}) {
		const itemCode = this.getItemCode(itemOrCode)
		const normalizedUom = this.normalize(uom)

		if (!itemCode || !normalizedUom) {
			return {
				ok: false,
				allowed: false,
				item_code: itemCode,
				uom: normalizedUom,
			}
		}

		try {
			const response = await call(this.methods.checkAllowed, {
				item_code: itemCode,
				uom: normalizedUom,
				mode: options.mode || this.mode,
			})

			return response?.message || response || {}
		} catch (error) {
			this.log("checkAllowed failed, falling back to cache", error)
			return {
				ok: true,
				allowed: this.isUomAllowed(itemCode, normalizedUom),
				item_code: itemCode,
				uom: normalizedUom,
				mode: options.mode || this.mode,
			}
		}
	}

	async validateBarcodeResult(result, options = {}) {
		if (!result) {
			return {
				ok: false,
				allowed: false,
				reason: "missing_result",
				result: null,
			}
		}

		const itemCode = this.getItemCode(result)
		const uom = this.normalize(
			result.uom || result.barcode_uom || result.scanned_uom || result.stock_uom,
		)

		if (!itemCode) {
			return {
				ok: false,
				allowed: false,
				reason: "missing_item_code",
				result,
			}
		}

		await this.ensurePolicyLoaded(itemCode, options)

		if (!uom) {
			return {
				ok: true,
				allowed: true,
				reason: null,
				result: await this.normalizeItemAsync(result, options),
				policy: this.getPolicy(itemCode),
			}
		}

		try {
			const response = await call(this.methods.validateBarcode, {
				item_code: itemCode,
				uom,
				mode: options.mode || this.mode,
			})

			const payload = response?.message || response || {}
			const policy = payload?.policy || this.getPolicy(itemCode)

			if (policy) {
				this.cachePolicy(itemCode, policy, result)
			}

			const allowed = !!payload?.allowed
			if (!allowed) {
				return {
					ok: false,
					allowed: false,
					reason: "barcode_uom_not_allowed",
					item_code: itemCode,
					uom,
					result,
					policy: this.getPolicy(itemCode),
				}
			}

			const normalizedItem = await this.normalizeItemAsync(
				{
					...result,
					uom,
				},
				options,
			)

			return {
				ok: true,
				allowed: true,
				reason: null,
				item_code: itemCode,
				uom,
				result: normalizedItem,
				policy: this.getPolicy(itemCode),
			}
		} catch (error) {
			this.log("validateBarcode failed, falling back to cache", error)

			const allowed = this.isBarcodeUomAllowed(itemCode, uom)
			if (!allowed) {
				return {
					ok: false,
					allowed: false,
					reason: "barcode_uom_not_allowed",
					item_code: itemCode,
					uom,
					result,
					policy: this.getPolicy(itemCode),
				}
			}

			return {
				ok: true,
				allowed: true,
				reason: null,
				item_code: itemCode,
				uom,
				result: await this.normalizeItemAsync(
					{
						...result,
						uom,
					},
					options,
				),
				policy: this.getPolicy(itemCode),
			}
		}
	}
}

export const uomPolicyAdapter = new UomPolicyAdapter()
export default uomPolicyAdapter