from uae_compliance.uae_compliance.utils.trn import validate_tin, validate_trn


def validate_trn_and_tin(doc, method=None):
	doc.uae_trn = validate_trn(doc.uae_trn, label=f"{doc.doctype} TRN")
	doc.uae_tin = validate_tin(doc.uae_tin, label=f"{doc.doctype} TIN")
