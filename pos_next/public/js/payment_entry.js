frappe.ui.form.on('Payment Entry', {
    refresh: function(frm) {
        fetch_opening_shift_reference(frm);
    }
});

frappe.ui.form.on('Payment Entry Reference', {
    reference_name: function(frm, cdt, cdn) {
        fetch_opening_shift_reference(frm);
    }
});

function fetch_opening_shift_reference(frm) {
    if (frm.doc.reference_no) return;

    (frm.doc.references || []).forEach(function(row) {
        if (row.reference_doctype === 'Sales Invoice' && row.reference_name) {
            frappe.db.get_value(
                'Sales Invoice',
                row.reference_name,
                'posa_pos_opening_shift',
                (r) => {
                    if (r && r.posa_pos_opening_shift && !frm.doc.reference_no) {
                        frm.set_value('reference_no', r.posa_pos_opening_shift);
                    }
                }
            );
        }
    });
}