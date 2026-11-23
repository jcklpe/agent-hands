"""github private settings contract; no authentication or service requests."""
from pathlib import Path
import sys
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE.parent/'setup-agent-hands/scripts'))
from private_settings import Settings, main
settings=Settings('github-settings', SOURCE, 'GITHUB', 'github-repos.json', 'GITHUB_REPOS_PATH')
if __name__=='__main__':main(settings)
