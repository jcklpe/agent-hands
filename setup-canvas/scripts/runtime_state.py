"""canvas private settings contract; no authentication or service requests."""
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE.parent/'setup-agent-hands/scripts'))
from private_settings import Settings, main
settings=Settings('canvas', SOURCE, 'CANVAS', 'canvas-accounts.json', patterns=('.env.canvas-renew-*',))
if __name__=='__main__':main(settings)
