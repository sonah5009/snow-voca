IRREGULAR = {
    "felt": "feel", "got": "get", "went": "go", "kept": "keep", "left": "leave",
    "found": "find", "made": "make", "took": "take", "came": "come", "said": "say",
    "stopped": "stop", "figured": "figure", "checked": "check", "counted": "count",
    "happened": "happen", "ordered": "order", "relaxed": "relax", "joined": "join",
    "scrolling": "scroll", "trying": "try", "leaving": "leave", "figuring": "figure",
}

def lemmatize(word: str) -> str:
    w = word.lower().strip(".,!?\"'")
    if w in IRREGULAR:
        return IRREGULAR[w]
    for suf, cut in (("ies", 3), ("ing", 3), ("ed", 2), ("es", 2), ("s", 1)):
        if w.endswith(suf) and len(w) - cut >= 3:
            stem = w[:-cut]
            if suf == "ies":
                return stem + "y"
            if suf in ("ing", "ed") and len(stem) > 2 and stem[-1] == stem[-2]:
                stem = stem[:-1]          # stopp → stop
            if suf == "ing" and stem in ("hav", "mak", "tak", "com", "writ"):
                stem += "e"
            return stem
    return w
