"""Create the local HELIOS SQLite schema and load configured cameras/zones."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import load_settings
from app.database.connection import connect
from app.services.helios_service import HeliosService

if __name__ == '__main__':
    settings=load_settings(); service=HeliosService(connect(settings.database_path),settings);service.seed()
    print(f'Initialized {settings.database_path}')
