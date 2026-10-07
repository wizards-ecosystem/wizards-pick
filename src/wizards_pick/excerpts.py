"""Bounded excerpts retain both invocation context and the final result."""


def excerpt(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    if budget < 80:
        raise ValueError("excerpt budget must be at least 80")
    keep = (budget - 80) // 2
    marker = f"\n[output excerpt truncated: {len(text) - keep * 2} characters omitted]\n"
    return text[:keep] + marker + text[-keep:]
