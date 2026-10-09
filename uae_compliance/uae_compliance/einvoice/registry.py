import json

import frappe
from frappe import _
from frappe.utils.password import get_decrypted_password

from uae_compliance.uae_compliance.einvoice.asp_client import ASPClient, ProviderConfig

_PROVIDERS: dict[str, type[ASPClient]] = {}


def register_provider(cls: type[ASPClient]) -> type[ASPClient]:
	"""Class decorator that makes an adapter selectable in UAE E-Invoice Settings."""
	if not cls.name:
		raise ValueError("A provider adapter needs a name")

	_PROVIDERS[cls.name] = cls
	return cls


def get_provider_names() -> list[str]:
	_load_adapters()
	return sorted(_PROVIDERS)


def get_provider_class(name: str) -> type[ASPClient]:
	_load_adapters()
	if name not in _PROVIDERS:
		frappe.throw(
			_("The e-invoicing provider {0} is not available. Choose one of: {1}").format(
				frappe.bold(name), ", ".join(sorted(_PROVIDERS))
			),
			title=_("Unknown Provider"),
		)

	return _PROVIDERS[name]


def get_company_setting(company: str):
	"""The enabled UAE E-Invoice Settings row of a company, if any."""
	settings = frappe.get_cached_doc("UAE E-Invoice Settings")
	for row in settings.companies:
		if row.company == company and row.enabled:
			return row

	return None


def get_client(company: str) -> ASPClient:
	"""The adapter configured for a company, built with its stored settings and credentials."""
	row = get_company_setting(company)
	if not row:
		frappe.throw(
			_("E-invoicing is not enabled for {0} in UAE E-Invoice Settings.").format(company),
			title=_("E-Invoicing Not Enabled"),
		)

	secret = get_decrypted_password(row.doctype, row.name, "client_secret", raise_exception=False)
	config = ProviderConfig(
		company=company,
		environment=row.environment,
		endpoint_url=row.endpoint_url or "",
		client_id=row.client_id or "",
		client_secret=secret or "",
		extra=json.loads(row.extra_config) if row.extra_config else {},
	)
	return get_provider_class(row.provider)(config)


def _load_adapters() -> None:
	# Importing a module registers the adapters in it. New adapters are listed here.
	from uae_compliance.uae_compliance.einvoice.asp_clients import mock
