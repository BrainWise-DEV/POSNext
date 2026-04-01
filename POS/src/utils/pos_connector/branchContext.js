import { firstNonEmpty } from "./shared"

export function getBranchContext(context = {}) {
	const profile = context.profile || {}
	const posProfile = context.posProfile || {}
	const session = context.session || {}

	const branch =
		firstNonEmpty(
			context.branch,
			profile.branch,
			profile.posa_branch,
			posProfile.branch,
			posProfile.posa_branch,
			session.branch,
		) || null

	return {
		branch,
		profile,
		posProfile,
		session,
	}
}

export function getBranchName(context = {}) {
	return getBranchContext(context).branch
}
