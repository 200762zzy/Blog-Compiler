class AIRewriter:
    def __init__(self, api_key: str = "", api_base: str = "", model: str = ""):
        self.api_key = api_key
        self.api_base = api_base
        self.model = model

    def rewrite(self, markdown_content: str) -> str:
        raise NotImplementedError("Phase 3 实现")
