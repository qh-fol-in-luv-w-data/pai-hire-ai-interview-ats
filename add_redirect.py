with open('/home/pai/pai-hire/backend/main.py', 'r') as f:
    content = f.read()

redirect_code = """
from fastapi.responses import RedirectResponse
@app.get("/v1/slot/{token}/validate", include_in_schema=False)
def redirect_v1_slot_validate(token: str):
    return RedirectResponse(url=f"/api/v1/slot/{token}/validate", status_code=307)
"""
if "redirect_v1_slot_validate" not in content:
    content += redirect_code
    with open('/home/pai/pai-hire/backend/main.py', 'w') as f:
        f.write(content)
        print("Success")
