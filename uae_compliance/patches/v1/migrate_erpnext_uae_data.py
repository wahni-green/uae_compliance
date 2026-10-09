from uae_compliance.uae_compliance.utils.migration import (
	migrate_master_data,
	migrate_purchase_reverse_charge,
	migrate_vat_settings,
)


def execute() -> None:
	migrate_vat_settings()
	migrate_master_data()
	migrate_purchase_reverse_charge()
