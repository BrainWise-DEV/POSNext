/**
 * Runtime API paths for optional POSNext Promotions.
 *
 * pos_next never imports the promotions Python package. Vue may call
 * posnext_promotions.api.* only when that app's extend_bootinfo flag is present.
 */

export function isPromotionsAppInstalled() {
	return Boolean(window.frappe?.boot?.posnext_promotions);
}

export function isAuthGateInstalled() {
	return Boolean(
		window.frappe?.boot?.posnext_promotions_auth || window.frappe?.boot?.posnext_promotions,
	);
}

function promoOrPos(promoPath, posPath) {
	return isPromotionsAppInstalled() ? promoPath : posPath;
}

function authOrPos(promoPath, posPath) {
	return isAuthGateInstalled() ? promoPath : posPath;
}

export const promoApi = {
	applyOffers: () =>
		promoOrPos("posnext_promotions.api.offers.apply_offers", "pos_next.api.invoices.apply_offers"),
	getOffers: () => promoOrPos("posnext_promotions.api.offers.get_offers", "pos_next.api.offers.get_offers"),
	validateCoupon: () =>
		promoOrPos("posnext_promotions.api.offers.validate_coupon", "pos_next.api.offers.validate_coupon"),
	getActiveCoupons: () =>
		promoOrPos(
			"posnext_promotions.api.offers.get_active_coupons",
			"pos_next.api.offers.get_active_coupons",
		),
	calculateCouponDiscount: () =>
		promoOrPos(
			"posnext_promotions.api.offers.calculate_coupon_discount",
			"pos_next.api.offers.calculate_coupon_discount",
		),
	itemHasActivePromotion: () =>
		promoOrPos(
			"posnext_promotions.api.offers.item_has_active_promotion",
			"pos_next.api.offers.item_has_active_promotion",
		),
	getCustomerOneTimeRedemptions: () =>
		promoOrPos(
			"posnext_promotions.api.offers.get_customer_one_time_redemptions",
			"pos_next.api.offers.get_customer_one_time_redemptions",
		),
	getPromotions: () =>
		promoOrPos("posnext_promotions.api.promotions.get_promotions", "pos_next.api.promotions.get_promotions"),
	getPromotionDetails: () =>
		promoOrPos(
			"posnext_promotions.api.promotions.get_promotion_details",
			"pos_next.api.promotions.get_promotion_details",
		),
	createPromotion: () =>
		promoOrPos(
			"posnext_promotions.api.promotions.create_promotion",
			"pos_next.api.promotions.create_promotion",
		),
	updatePromotion: () =>
		promoOrPos(
			"posnext_promotions.api.promotions.update_promotion",
			"pos_next.api.promotions.update_promotion",
		),
	togglePromotion: () =>
		promoOrPos(
			"posnext_promotions.api.promotions.toggle_promotion",
			"pos_next.api.promotions.toggle_promotion",
		),
	deletePromotion: () =>
		promoOrPos(
			"posnext_promotions.api.promotions.delete_promotion",
			"pos_next.api.promotions.delete_promotion",
		),
	getItemGroups: () =>
		promoOrPos("posnext_promotions.api.promotions.get_item_groups", "pos_next.api.promotions.get_item_groups"),
	getBrands: () =>
		promoOrPos("posnext_promotions.api.promotions.get_brands", "pos_next.api.promotions.get_brands"),
	getCoupons: () =>
		promoOrPos("posnext_promotions.api.promotions.get_coupons", "pos_next.api.promotions.get_coupons"),
	getCouponDetails: () =>
		promoOrPos(
			"posnext_promotions.api.promotions.get_coupon_details",
			"pos_next.api.promotions.get_coupon_details",
		),
	createCoupon: () =>
		promoOrPos("posnext_promotions.api.promotions.create_coupon", "pos_next.api.promotions.create_coupon"),
	updateCoupon: () =>
		promoOrPos("posnext_promotions.api.promotions.update_coupon", "pos_next.api.promotions.update_coupon"),
	toggleCoupon: () =>
		promoOrPos("posnext_promotions.api.promotions.toggle_coupon", "pos_next.api.promotions.toggle_coupon"),
	deleteCoupon: () =>
		promoOrPos("posnext_promotions.api.promotions.delete_coupon", "pos_next.api.promotions.delete_coupon"),
	getAuthorizers: () =>
		authOrPos(
			"posnext_promotions.api.authorization.get_authorizers",
			"pos_next.api.authorization.get_authorizers",
		),
	requestGrant: () =>
		authOrPos(
			"posnext_promotions.api.authorization.request_grant",
			"pos_next.api.authorization.request_grant",
		),
	getAuthorizationPolicy: () =>
		authOrPos(
			"posnext_promotions.api.authorization.get_authorization_policy",
			"pos_next.api.authorization.get_authorization_policy",
		),
	hasAuthorizationPin: () =>
		authOrPos(
			"posnext_promotions.api.authorization.has_authorization_pin",
			"pos_next.api.authorization.has_authorization_pin",
		),
};
