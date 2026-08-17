class PathRewriteMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith("/v1/"):
                scope["path"] = "/api" + path
                if b"raw_path" in scope:
                    scope["raw_path"] = b"/api" + scope["raw_path"]
        await self.app(scope, receive, send)
