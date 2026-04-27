export const Stronghold = {
	load: async () => ({
		loadClient: async () => ({
			getStore: () => ({
				get: async () => null,
				insert: async () => {},
				remove: async () => {},
			}),
		}),
		createClient: async () => ({
			getStore: () => ({
				get: async () => null,
				insert: async () => {},
				remove: async () => {},
			}),
		}),
		save: async () => {},
	}),
}
