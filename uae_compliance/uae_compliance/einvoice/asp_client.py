"""The interface every Accredited Service Provider (ASP) adapter implements.

A company sends its e-invoices through one ASP, which signs them, sends them over the Peppol network
and reports them to the FTA. The ASPs differ in transport, authentication and response format, so
everything provider specific lives in an adapter: the app builds and validates the PINT AE XML itself
and talks to a provider only through this interface, with statuses normalized to
uae_compliance.constants.einvoice."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
	"""What an adapter is configured with, from UAE E-Invoice Settings."""

	company: str
	environment: str
	endpoint_url: str = ""
	client_id: str = ""
	client_secret: str = ""
	extra: dict = field(default_factory=dict)


@dataclass
class OutgoingDocument:
	"""A document ready to send, in both forms providers ask for: the PINT AE XML, and the same
	invoice as plain data (see PintAEBuilder.build_all) for providers whose API takes the invoice's
	fields rather than a document. Both carry the same figures."""

	number: str
	uuid: str
	xml: bytes
	model: dict
	metadata: dict = field(default_factory=dict)


@dataclass
class SubmitResult:
	provider_reference: str
	status: str
	detail: str = ""
	raw_response: str = ""


@dataclass
class StatusResult:
	status: str
	detail: str = ""
	raw_response: str = ""


@dataclass
class InboundDocument:
	"""An e-invoice received for the company, as delivered by the provider: a PINT AE XML document,
	or for providers that hand over the invoice's fields instead, a model with the keys of
	`inbound.parse_document` (kind, type_code, number, uuid, issue_date, currency, seller_*, buyer_*,
	tax_total, payable, lines)."""

	provider_reference: str
	xml: bytes | None = None
	model: dict | None = None


class ASPClient(ABC):
	"""Raise ServiceProviderError (or a subclass) for a failure worth retrying, such as a timeout or
	a rate limit, and ProviderRejectedError when the provider refuses the document for good."""

	#: Registry name, shown in UAE E-Invoice Settings.
	name: str = ""
	#: Settings the adapter cannot work without; checked when the settings are saved.
	required_settings: tuple[str, ...] = ()

	def __init__(self, config: ProviderConfig):
		self.config = config

	@abstractmethod
	def submit(self, document: OutgoingDocument, idempotency_key: str) -> SubmitResult:
		"""Send a document. Use whichever form the provider takes. Sending the same idempotency key
		twice must not create a second invoice at the provider."""

	@abstractmethod
	def get_status(self, provider_reference: str) -> StatusResult:
		"""The current normalized status of a submitted document."""

	def fetch_inbound(self, known_references: set[str] | None = None) -> list[InboundDocument]:
		"""Documents received for the company. `known_references` are the provider references already
		logged, which an adapter can skip instead of fetching their details again. Not every provider
		supports receiving."""
		return []

	def validate_credentials(self) -> None:
		"""Raise if the configured credentials do not work."""
		return None
