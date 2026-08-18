/**
 * Magento LP is present when magento_integration is installed.
 * Vanilla develop Vue has no Magento UI unless this returns true.
 */
export function isMagentoAppInstalled() {
	try {
		return Boolean(window.frappe?.boot?.magento_integration || window.magento_integration);
	} catch {
		return false;
	}
}
