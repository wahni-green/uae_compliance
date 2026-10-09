frappe.ui.form.on("UAE VAT Return", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Download FAF"), () => {
			open_url_post(
				"/api/method/run_doc_method",
				{ docs: JSON.stringify(frm.doc), method: "download_faf" },
				true
			);
		});

		if (frm.doc.status !== "Draft") return;

		frm.add_custom_button(__("Generate Return"), () => {
			frm.call("generate_return").then(() => frm.reload_doc());
		});

		if (frm.doc.boxes && frm.doc.boxes.length) {
			frm.add_custom_button(__("Mark as Filed"), () => {
				frappe.confirm(
					__(
						"Filing this return locks it permanently. It can no longer be edited, regenerated or deleted. Continue?"
					),
					() => frm.call("mark_as_filed").then(() => frm.reload_doc())
				);
			});
		}
	},
});
