from uae_compliance.uae_compliance.setup import (
	create_custom_fields,
	create_designated_zones,
	hide_erpnext_uae_fields,
	set_default_settings,
)
from uae_compliance.uae_compliance.utils.migration import (
	migrate_item_vat_flags,
	migrate_master_data,
	migrate_purchase_reverse_charge,
	migrate_vat_settings,
)


def after_install() -> None:
	create_custom_fields()
	create_designated_zones()
	set_default_settings()
	hide_erpnext_uae_fields()

	# Patches don't run on a fresh install, so migrate any existing ERPNext UAE data here too.
	# All of these are idempotent.
	migrate_item_vat_flags()
	migrate_vat_settings()
	migrate_master_data()
	migrate_purchase_reverse_charge()
