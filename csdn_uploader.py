class CSDNUploader:
    def __init__(self):
        self.cookies = {}

    def login_with_cookies(self, cookies: dict):
        self.cookies = cookies

    def upload_image(self, local_path: str) -> str:
        raise NotImplementedError("Phase 2 实现")
