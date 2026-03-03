"""脱敏等辅助。"""


def mask_secret(value: str | None, visible: int = 4, placeholder: str = "***") -> str:
    """密钥脱敏：保留前 visible 字符 + placeholder。"""
    if value is None or not value.strip():
        return placeholder
    s = value.strip()
    if len(s) <= visible:
        return placeholder
    return s[:visible] + placeholder
