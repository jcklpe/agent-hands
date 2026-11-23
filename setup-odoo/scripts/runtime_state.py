"""odoo private settings contract; no authentication or service requests."""
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE.parent/'setup-agent-hands/scripts'))
from private_settings import Settings, main
settings=Settings('odoo', SOURCE, 'ODOO', 'odoo-accounts.json', 'ODOO_ACCOUNTS_PATH', extra_keys={'ODOO_REQUEST_STATE_PATH':'odoo-last-request'})
if __name__=='__main__':main(settings)
