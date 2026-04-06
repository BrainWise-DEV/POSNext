// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sync Site Config", {
	refresh(frm) {
		if (frm.doc.site_role === "Branch" && !frm.is_new()) {
			frm.add_custom_button(__("Test Sync Connection"), () => {
				frappe.call({
					doc: frm.doc,
					method: "test_connection",
					freeze: true,
					freeze_message: __("Testing connection..."),
					callback(r) {
						if (!r.message) return;
						const msg = r.message.message;
						const ok = r.message.ok;
						frappe.msgprint({
							title: ok ? __("Connection OK") : __("Connection Failed"),
							message: msg,
							indicator: ok ? "green" : "red",
						});
					},
				});
			});
		}

		// Show sync status dashboard
		if (!frm.is_new()) {
			frm.trigger("load_sync_dashboard");
		}
	},

	load_sync_dashboard(frm) {
		frappe.call({
			method: "pos_next.sync.api.status.get_sync_status",
			callback(r) {
				if (!r.message || !r.message.configured) return;
				const data = r.message;
				frm.dashboard.clear_headline();

				// Build status HTML
				let html = `<div class="sync-dashboard" style="padding: 10px 0;">`;

				// Last pull info
				if (data.last_pull_masters_at) {
					html += `<div style="margin-bottom: 8px;">
						<strong>${__("Last Masters Pull")}:</strong>
						${frappe.datetime.prettyDate(data.last_pull_masters_at)}
					</div>`;
				}

				// Error banner
				if (data.last_sync_error) {
					html += `<div class="alert alert-danger" style="margin-bottom: 8px;">
						<strong>${__("Last Error")}:</strong> ${data.last_sync_error}
					</div>`;
				}

				// Outbox stats
				html += `<div style="margin-bottom: 8px;">
					<strong>${__("Outbox")}:</strong>
					${data.outbox.pending} ${__("pending")},
					${data.outbox.failed} ${__("failed")},
					${data.outbox.dead} ${__("dead letter")}
				</div>`;

				// Conflicts
				if (data.conflicts_pending > 0) {
					html += `<div class="alert alert-warning" style="margin-bottom: 8px;">
						<strong>${data.conflicts_pending}</strong> ${__("unresolved sync conflicts")}
					</div>`;
				}

				// Watermarks table
				if (data.watermarks && data.watermarks.length > 0) {
					html += `<details style="margin-top: 10px;">
						<summary><strong>${__("Watermarks")} (${data.watermarks.length} ${__("DocTypes")})</strong></summary>
						<table class="table table-bordered table-condensed" style="margin-top: 5px; font-size: 12px;">
							<thead><tr>
								<th>${__("DocType")}</th>
								<th>${__("Last Modified")}</th>
								<th>${__("Last Pulled")}</th>
								<th>${__("Records")}</th>
							</tr></thead><tbody>`;
					data.watermarks.forEach(w => {
						html += `<tr>
							<td>${w.doctype_name}</td>
							<td>${w.last_modified ? frappe.datetime.prettyDate(w.last_modified) : "-"}</td>
							<td>${w.last_pulled_at ? frappe.datetime.prettyDate(w.last_pulled_at) : "-"}</td>
							<td>${w.records_pulled || 0}</td>
						</tr>`;
					});
					html += `</tbody></table></details>`;
				}

				// Recent logs
				if (data.recent_logs && data.recent_logs.length > 0) {
					html += `<details style="margin-top: 10px;">
						<summary><strong>${__("Recent Sync Logs")} (${data.recent_logs.length})</strong></summary>
						<table class="table table-bordered table-condensed" style="margin-top: 5px; font-size: 12px;">
							<thead><tr>
								<th>${__("Operation")}</th>
								<th>${__("Status")}</th>
								<th>${__("Duration")}</th>
								<th>${__("Records")}</th>
								<th>${__("When")}</th>
							</tr></thead><tbody>`;
					data.recent_logs.forEach(log => {
						const indicator = log.status === "success" ? "green" : log.status === "failure" ? "red" : "orange";
						html += `<tr>
							<td>${log.operation}</td>
							<td><span class="indicator-pill ${indicator}">${log.status}</span></td>
							<td>${log.duration_ms || 0}ms</td>
							<td>${log.records_touched || 0}</td>
							<td>${frappe.datetime.prettyDate(log.creation)}</td>
						</tr>`;
					});
					html += `</tbody></table></details>`;
				}

				html += `</div>`;
				frm.dashboard.set_headline_alert(html);
			},
		});
	},
});
