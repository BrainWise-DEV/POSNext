/**
 * Invoice utility functions
 * Common helpers for invoice-related operations across the application
 */

/**
 * Get the appropriate CSS classes for invoice status badge
 * @param {Object} invoice - Invoice object with status and docstatus fields
 * @returns {string} Tailwind CSS classes for the status badge
 */
export function getInvoiceStatusColor(invoice) {
	const status = invoice.status?.toLowerCase()

	// Red for overdue, cancelled
	if (status === 'overdue' || invoice.docstatus === 2) {
		return 'bg-red-100 text-red-800'
	}

	// Orange for partly paid (partial payment received)
	if (status === 'partly paid' || status === 'partially paid') {
		return 'bg-orange-100 text-orange-800'
	}

	// Yellow for unpaid
	if (status === 'unpaid') {
		return 'bg-yellow-100 text-yellow-800'
	}

	// Blue for credit note issued
	if (status === 'credit note issued') {
		return 'bg-blue-100 text-blue-800'
	}

	// Green for paid, submitted
	if (status === 'paid' || invoice.docstatus === 1) {
		return 'bg-green-100 text-green-800'
	}

	// Gray for draft and others
	return 'bg-gray-100 text-gray-800'
}

/**
 * Get status color theme name for use with Badge component
 * @param {string} status - Invoice status string
 * @returns {string} Theme name (red, yellow, blue, green, gray)
 */
export function getInvoiceStatusTheme(status) {
	const statusLower = status?.toLowerCase()

	if (statusLower === 'overdue' || statusLower === 'cancelled') {
		return 'red'
	}

	if (statusLower === 'partly paid' || statusLower === 'partially paid') {
		return 'orange'
	}

	if (statusLower === 'unpaid') {
		return 'yellow'
	}

	if (statusLower === 'credit note issued') {
		return 'blue'
	}

	if (statusLower === 'paid') {
		return 'green'
	}

	return 'gray'
}
