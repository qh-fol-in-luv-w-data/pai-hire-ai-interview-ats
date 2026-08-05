import sys
sys.path.append("/home/pai/pai-hire")
from backend.main import app
for route in app.routes:
    print(getattr(route, "path", ""))
