"""google-services private settings contract; no authentication or service requests."""
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE.parent/'setup-agent-hands/scripts'))
from private_settings import Settings, main
settings=Settings('google', SOURCE, 'GOOGLE', 'google-accounts.json', 'GOOGLE_ACCOUNTS_PATH', fields=(('credentials_path','google-credentials.json'),('token_path',None)), extra_files=((SOURCE.parent/'use-gmail/mail-writes.jsonl','gmail-audit.jsonl'),))
if __name__=='__main__':main(settings)
