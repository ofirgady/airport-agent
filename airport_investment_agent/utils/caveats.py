def merge_unique(*caveat_lists: list[str]) -> list[str]:
    """Flatten multiple caveat lists into one, keeping first-seen order and
    dropping exact-duplicate strings."""
    merged: list[str] = []
    for caveats in caveat_lists:
        for caveat in caveats:
            if caveat not in merged:
                merged.append(caveat)
    return merged
