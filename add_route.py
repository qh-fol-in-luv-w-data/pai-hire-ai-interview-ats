with open('/home/pai/pai-hire/backend/routers/api_v1.py', 'r') as f:
    content = f.read()

# Find the validate route and add a second @router.get decorator for /v1/slot
if "@router.get(\"/slot/{token}/validate\")" in content:
    content = content.replace(
        "@router.get(\"/slot/{token}/validate\")",
        "@router.get(\"/slot/{token}/validate\")\n@router.get(\"/{token}/validate\")"
    )
    with open('/home/pai/pai-hire/backend/routers/api_v1.py', 'w') as f:
        f.write(content)
        print("Success")
