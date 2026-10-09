/**
 * Hour-of-day windows for offers — the client half of `pos_next/promotions/schedule.py`.
 *
 * The server ships each offer's window as `{from_time, to_time}` (absent when the
 * offer runs at any hour) and evaluates it in the **system timezone**. This module
 * reads the clock in that same zone so an offer switches on and off at the same
 * instant on the counter as it does on the server, whatever the device is set to.
 *
 * Semantics mirror the Python side exactly:
 *   - no window            -> always active
 *   - from === to          -> all day
 *   - from  <  to          -> inside the range
 *   - from  >  to          -> wraps past midnight (22:00 -> 02:00)
 */

const SECONDS_PER_DAY = 24 * 60 * 60;

/** Seconds since midnight for "HH:MM:SS", or null if unusable. */
function toSeconds(value) {
	if (!value) return null;
	const parts = String(value).split(":");
	if (parts.length < 2) return null;
	const [h, m, s] = parts;
	const hours = Number.parseInt(h, 10);
	const minutes = Number.parseInt(m, 10);
	const seconds = Number.parseInt(s ?? "0", 10);
	if (Number.isNaN(hours) || Number.isNaN(minutes)) return null;
	return hours * 3600 + minutes * 60 + (Number.isNaN(seconds) ? 0 : seconds);
}

/**
 * Seconds since midnight *in the given timezone*.
 * @param {string|null} timezone - IANA zone; the device's own zone when null
 * @param {Date} [now]
 */
export function secondsSinceMidnight(timezone, now = new Date()) {
	try {
		const parts = new Intl.DateTimeFormat("en-GB", {
			timeZone: timezone || undefined,
			hour12: false,
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
		}).formatToParts(now);
		const get = (type) => Number.parseInt(parts.find((p) => p.type === type)?.value ?? "0", 10);
		let hour = get("hour");
		if (hour === 24) hour = 0; // some engines render midnight as 24
		return hour * 3600 + get("minute") * 60 + get("second");
	} catch {
		return now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
	}
}

/** The `{from_time, to_time}` an offer carries, or null when unrestricted. */
export function getOfferWindow(offer) {
	const schedule = offer?.schedule;
	if (!schedule) return null;

	const from = toSeconds(schedule.from_time);
	const to = toSeconds(schedule.to_time);
	if (from === null || to === null || from === to) return null;

	return { from, to };
}

/**
 * Whether an offer's hour window is open.
 * @param {Object} offer
 * @param {string|null} timezone - the site's system timezone
 */
export function isOfferInSchedule(offer, timezone, now = new Date()) {
	const window = getOfferWindow(offer);
	if (!window) return true;

	const current = secondsSinceMidnight(timezone, now);
	return window.from < window.to
		? current >= window.from && current <= window.to
		: current >= window.from || current <= window.to;
}

/**
 * Milliseconds until the next moment any of these offers opens or closes.
 *
 * Lets the cart schedule a single timer that fires exactly on the boundary,
 * rather than polling. Returns null when no offer has a window.
 */
export function msUntilNextScheduleBoundary(offers, timezone, now = new Date()) {
	const current = secondsSinceMidnight(timezone, now);
	let smallest = null;

	for (const offer of offers || []) {
		const window = getOfferWindow(offer);
		if (!window) continue;

		for (const edge of [window.from, window.to]) {
			// +1s so the timer lands just *after* the boundary, never a hair before.
			let delta = edge - current + 1;
			if (delta <= 0) delta += SECONDS_PER_DAY;
			if (smallest === null || delta < smallest) smallest = delta;
		}
	}

	return smallest === null ? null : smallest * 1000;
}
