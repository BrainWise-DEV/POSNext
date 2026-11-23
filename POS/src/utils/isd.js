// Frappe's country_info has dummy ISDs ("+0") and a stray space ("+ 345").
// A usable ISD is "+" then 1-4 digits, first digit non-zero.
const VALID_ISD = /^\+[1-9]\d{0,3}$/;

export function normalizeIsd(isd) {
	return String(isd ?? "").replace(/\s+/g, "");
}

export function isValidIsd(isd) {
	return VALID_ISD.test(normalizeIsd(isd));
}

// Shared by the countries store and useCountryCodes so both parse identically.
export function parsePhoneNumberWith(fullNumber, countryList) {
	const raw = String(fullNumber ?? "").trim();
	if (!raw) return { isd: "", number: "" };

	// Preferred stored format: +20-1012345678
	if (raw.includes("-")) {
		const [head, ...rest] = raw.split("-");
		const isd = normalizeIsd(head);
		if (isValidIsd(isd)) return { isd, number: rest.join("-") };
		// Bogus prefix ("+0-123"): drop it, keep the digits after it
		if (head.trim().startsWith("+")) return { isd: "", number: rest.join("").replace(/\D/g, "") };
		return { isd: "", number: raw.replace(/\D/g, "") };
	}

	// Legacy / pasted: +201012345678 (ISD prefix, no separator)
	if (raw.startsWith("+")) {
		const match = countryList
			.filter((c) => isValidIsd(c.isd) && raw.startsWith(c.isd))
			.sort((a, b) => b.isd.length - a.isd.length)[0];
		if (match) return { isd: match.isd, number: raw.slice(match.isd.length) };
	}

	return { isd: "", number: raw.replace(/\D/g, "") };
}
