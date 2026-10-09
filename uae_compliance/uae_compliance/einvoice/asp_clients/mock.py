import json

import frappe

from uae_compliance.exceptions import GatewayTimeoutError
from uae_compliance.uae_compliance.constants.einvoice import (
	STATUS_CLEARED,
	STATUS_DELIVERED,
	STATUS_REJECTED,
	STATUS_SUBMITTED,
)
from uae_compliance.uae_compliance.einvoice.asp_client import (
	ASPClient,
	InboundDocument,
	OutgoingDocument,
	StatusResult,
	SubmitResult,
)
from uae_compliance.uae_compliance.einvoice.registry import register_provider

_CACHE_KEY = "uae_compliance_mock_asp"


@register_provider
class MockASP(ASPClient):
	"""A provider that talks to nobody, for development, sandboxes and tests.

	`behavior` in the extra configuration decides what happens: `clear` (default) moves a document
	through submitted, delivered and cleared on successive status checks, `reject` rejects it,
	`timeout` raises a transient error on submission. Documents are remembered by idempotency key, so
	a repeated submission returns the same reference."""

	name = "Mock"

	@property
	def behavior(self) -> str:
		return self.config.extra.get("behavior", "clear")

	def _store(self) -> dict:
		return json.loads(frappe.cache().get_value(_CACHE_KEY) or "{}")

	def _save(self, store: dict) -> None:
		frappe.cache().set_value(_CACHE_KEY, json.dumps(store))

	def submit(self, document: OutgoingDocument, idempotency_key: str) -> SubmitResult:
		if self.behavior == "timeout":
			raise GatewayTimeoutError("The mock provider timed out")

		store = self._store()
		reference = f"MOCK-{idempotency_key}"
		store.setdefault(reference, {"checks": 0, "bytes": len(document.xml)})
		self._save(store)
		return SubmitResult(provider_reference=reference, status=STATUS_SUBMITTED, detail="Accepted")

	def get_status(self, provider_reference: str) -> StatusResult:
		store = self._store()
		entry = store.get(provider_reference)
		if entry is None:
			return StatusResult(status=STATUS_REJECTED, detail="Unknown reference")

		if self.behavior == "reject":
			return StatusResult(status=STATUS_REJECTED, detail="Rejected by the mock provider")

		entry["checks"] += 1
		self._save(store)
		status = STATUS_DELIVERED if entry["checks"] == 1 else STATUS_CLEARED
		return StatusResult(status=status, detail=f"Check {entry['checks']}")

	def fetch_inbound(self) -> list[InboundDocument]:
		return [
			InboundDocument(provider_reference=reference, xml=xml.encode())
			for reference, xml in self.config.extra.get("inbound", {}).items()
		]
