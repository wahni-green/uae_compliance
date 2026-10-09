# Statuses of an e-invoice, normalized across providers. Cleared is the terminal success: the
# invoice has passed the network and been reported to the FTA.
STATUS_PENDING = "Pending"
STATUS_GENERATED = "Generated"
STATUS_INVALID = "Invalid"
STATUS_SUBMITTED = "Submitted"
STATUS_DELIVERED = "Delivered"
STATUS_CLEARED = "Cleared"
STATUS_REJECTED = "Rejected"
STATUS_FAILED = "Failed"

STATUSES = [
	STATUS_PENDING,
	STATUS_GENERATED,
	STATUS_INVALID,
	STATUS_SUBMITTED,
	STATUS_DELIVERED,
	STATUS_CLEARED,
	STATUS_REJECTED,
	STATUS_FAILED,
]
STATUS_SELECT_OPTIONS = "\n".join(STATUSES)

# Once an invoice has been sent it can no longer be cancelled: a credit note corrects it.
SENT_STATUSES = (STATUS_SUBMITTED, STATUS_DELIVERED, STATUS_CLEARED)
# Statuses the scheduler still has work to do on.
SUBMIT_PENDING_STATUSES = (STATUS_GENERATED,)
POLL_STATUSES = (STATUS_SUBMITTED, STATUS_DELIVERED)

DIRECTION_OUTBOUND = "Outbound"
DIRECTION_INBOUND = "Inbound"

ENVIRONMENTS = ["Sandbox", "Production"]

# Transient failures are retried with exponential backoff: 1, 2, 4, 8, 16 minutes ...
DEFAULT_RETRY_LIMIT = 5
BACKOFF_MINUTES = 1

# E-invoices are kept for five years (MoF Guidelines section 5.4); the log may not be deleted before.
RETENTION_YEARS = 5
