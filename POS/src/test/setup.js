const storage = new Map();

globalThis.localStorage = {
	getItem: (key) => (storage.has(key) ? storage.get(key) : null),
	setItem: (key, value) => {
		storage.set(key, String(value));
	},
	removeItem: (key) => {
		storage.delete(key);
	},
	clear: () => {
		storage.clear();
	},
};
