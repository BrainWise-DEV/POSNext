// Copyright (c) 2025, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on('BrainWise Branding', {
	refresh: function(frm) {
		// Add custom buttons and UI elements
		add_master_key_controls(frm);

		// Lock/unlock fields based on master key
		update_field_permissions(frm);

		// Add warning indicators
		add_security_indicators(frm);
	},

	master_key_provided: function(frm) {
		// When master key is entered, unlock the protected fields
		if (frm.doc.master_key_provided) {
			unlock_protected_fields(frm);
			frm.dashboard.add_comment('Master key detected. Protected fields are now editable.', 'blue', true);
		}
	},

	enabled: function(frm) {
		// When trying to disable, show warning
		if (!frm.doc.enabled) {
			frappe.msgprint({
				title: __('Master Key Required'),
				indicator: 'red',
				message: __('To disable branding, you must provide the Master Key in JSON format: <code>{"key": "...", "phrase": "..."}</code>')
			});
		}
	}
});

function add_master_key_controls(frm) {
	// Add verify key button
	frm.add_custom_button(__('Verify Master Key'), function() {
		verify_master_key(frm);
	}, __('Actions'));

	// Add help button
	frm.add_custom_button(__('Master Key Help'), function() {
		show_master_key_help();
	}, __('Help'));

	// Add tampering stats button (System Manager only)
	if (frappe.user.has_role('System Manager')) {
		frm.add_custom_button(__('View Tampering Stats'), function() {
			show_tampering_stats();
		}, __('Security'));
	}
}

function update_field_permissions(frm) {
	// Protected fields
	const protected_fields = ['enabled', 'brand_text', 'brand_name', 'brand_url', 'check_interval'];

	// If master key is not provided, ensure fields are read-only
	if (!frm.doc.master_key_provided) {
		protected_fields.forEach(field => {
			frm.set_df_property(field, 'read_only', 1);
		});
	}
}

function unlock_protected_fields(frm) {
	// Temporarily unlock protected fields when master key is provided
	const protected_fields = ['enabled', 'brand_text', 'brand_name', 'brand_url', 'check_interval'];

	protected_fields.forEach(field => {
		frm.set_df_property(field, 'read_only', 0);
	});

	frappe.show_alert({
		message: __('Protected fields unlocked. You can now make changes.'),
		indicator: 'green'
	}, 5);
}

function verify_master_key(frm) {
	if (!frm.doc.master_key_provided) {
		frappe.msgprint({
			title: __('No Master Key Provided'),
			indicator: 'red',
			message: __('Please enter the Master Key in the field above to verify.')
		});
		return;
	}

	frappe.call({
		method: 'pos_next.pos_next.doctype.brainwise_branding.brainwise_branding.verify_master_key',
		args: {
			master_key_input: frm.doc.master_key_provided
		},
		callback: function(r) {
			if (r.message && r.message.valid) {
				frappe.show_alert({
					message: __('✅ Master Key is VALID! You can now modify protected fields.'),
					indicator: 'green'
				}, 10);

				// Unlock fields
				unlock_protected_fields(frm);
			} else {
				frappe.msgprint({
					title: __('Invalid Master Key'),
					indicator: 'red',
					message: __('The master key you provided is invalid. Please check and try again.<br><br>Format: <code>{"key": "...", "phrase": "..."}</code>')
				});
			}
		}
	});
}

function show_master_key_help() {
	const help_html = `
		<div class="master-key-help">
			<h4>🔐 Master Key System</h4>
			<p>The BrainWise branding is protected by a cryptographic master key system.</p>

			<h5>Protected Fields:</h5>
			<ul>
				<li><strong>Enabled:</strong> Cannot disable without master key</li>
				<li><strong>Brand Text:</strong> Cannot modify without master key</li>
				<li><strong>Brand Name:</strong> Cannot modify without master key</li>
				<li><strong>Brand URL:</strong> Cannot modify without master key</li>
				<li><strong>Check Interval:</strong> Cannot modify without master key</li>
			</ul>

			<h5>How to Use Master Key:</h5>
			<ol>
				<li>Obtain the master key from your secure storage</li>
				<li>Enter it in the "Master Key (JSON)" field in this format:<br>
					<code>{"key": "your-key-here", "phrase": "your-phrase-here"}</code>
				</li>
				<li>Click "Verify Master Key" to test (optional)</li>
				<li>Make your changes to protected fields</li>
				<li>Save the document</li>
			</ol>

			<h5>Security Features:</h5>
			<ul>
				<li>✅ Master key is never stored in database</li>
				<li>✅ All attempts are logged with audit trail</li>
				<li>✅ Dual-factor: requires both key and phrase</li>
				<li>✅ SHA-256 cryptographic hashing</li>
				<li>✅ Auto-locks fields after save</li>
			</ul>

			<div class="alert alert-warning">
				<strong>⚠️ Lost Your Master Key?</strong><br>
				Contact BrainWise support at <a href="mailto:support@brainwise.me">support@brainwise.me</a>
			</div>
		</div>
	`;

	frappe.msgprint({
		title: __('Master Key Help'),
		message: help_html,
		wide: true
	});
}

function show_tampering_stats() {
	frappe.call({
		method: 'pos_next.api.branding.get_tampering_stats',
		callback: function(r) {
			if (r.message) {
				const stats = r.message;
				const stats_html = `
					<div class="tampering-stats">
						<h4>📊 Branding Security Statistics</h4>
						<table class="table table-bordered">
							<tr>
								<th>Metric</th>
								<th>Value</th>
							</tr>
							<tr>
								<td>Branding Enabled</td>
								<td>${stats.enabled ? '<span class="indicator green">Yes</span>' : '<span class="indicator red">No</span>'}</td>
							</tr>
							<tr>
								<td>Total Tampering Attempts</td>
								<td><strong>${stats.tampering_attempts || 0}</strong></td>
							</tr>
							<tr>
								<td>Last Validation</td>
								<td>${stats.last_validation || 'Never'}</td>
							</tr>
							<tr>
								<td>Server Validation</td>
								<td>${stats.server_validation ? '<span class="indicator green">Enabled</span>' : '<span class="indicator orange">Disabled</span>'}</td>
							</tr>
							<tr>
								<td>Logging Enabled</td>
								<td>${stats.logging_enabled ? '<span class="indicator green">Yes</span>' : '<span class="indicator orange">No</span>'}</td>
							</tr>
						</table>
						<p class="text-muted">View detailed logs in <a href="/app/error-log?title=BrainWise%20Branding">Error Log</a></p>
					</div>
				`;

				frappe.msgprint({
					title: __('Security Statistics'),
					message: stats_html,
					wide: true
				});
			}
		}
	});
}

function add_security_indicators(frm) {
	// Add security indicator to dashboard
	if (frm.doc.enabled) {
		frm.dashboard.add_indicator(__('Branding Active'), 'green');
	} else {
		frm.dashboard.add_indicator(__('Branding Disabled'), 'red');
	}

	// Add tampering indicator if there are attempts
	if (frm.doc.tampering_attempts > 0) {
		frm.dashboard.add_indicator(__('Tampering Attempts: {0}', [frm.doc.tampering_attempts]), 'orange');
	}

	// Add protection indicator
	frm.dashboard.add_indicator(__('🔒 Master Key Protected'), 'blue');
}
