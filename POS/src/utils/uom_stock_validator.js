export function get_conversion_factor(item, uom) {
    if (!item?.uom_conversions) return 1;

    const row = item.uom_conversions.find(u => u.uom === uom);
    return row?.conversion_factor || 1;
}

export function get_available_stock(item) {
    // adapt based on your structure
    return item.actual_qty || item.stock_qty || 0;
}

export function is_stock_enforced(item) {
    return !item.sell_out_of_stock;
}

export function is_uom_stock_valid({ item, uom, qty }) {
    const conversion_factor = get_conversion_factor(item, uom);
    const required_qty = qty * conversion_factor;

    const available_stock = get_available_stock(item);

    if (!is_stock_enforced(item)) return true;

    return required_qty <= available_stock;
}

export function get_valid_uoms({ item, qty, allowed_uoms }) {
    return allowed_uoms.filter(uom =>
        is_uom_stock_valid({ item, uom, qty })
    );
}