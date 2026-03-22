/**
 * QZ Tray API - replaces pos_next.api.qz
 * In Electron, printing is handled natively via IPC.
 * These stubs exist for frontend compatibility.
 */

async function getCertificate() {
	return { certificate: null, message: "Desktop mode uses native printing" }
}

async function getCertificateDownload() {
	return null
}

async function signMessage(params) {
	return { signature: null }
}

async function setupQzCertificate() {
	return { success: true, message: "Not needed in desktop mode" }
}

module.exports = { getCertificate, getCertificateDownload, signMessage, setupQzCertificate }
