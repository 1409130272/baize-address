try:
    from pypinyin import lazy_pinyin
    _HAS_PYPINYIN = True
except ImportError:
    _HAS_PYPINYIN = False


def levenshtein(s1, s2):
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def to_pinyin(text):
    if not _HAS_PYPINYIN or not text:
        return ""
    return "".join(lazy_pinyin(text))


def pinyin_equal(s1, s2):
    if not _HAS_PYPINYIN:
        return False
    return to_pinyin(s1) == to_pinyin(s2)


def fuzzy_match(candidate, target_list, max_distance=2):
    results = []
    if not candidate:
        return results
    cand_py = to_pinyin(candidate) if _HAS_PYPINYIN else ""
    for info in target_list:
        name = info.name
        if abs(len(name) - len(candidate)) > max_distance:
            continue
        dist = levenshtein(candidate, name)
        if dist <= max_distance:
            score = 60 - dist * 10
            results.append((info, score, "edit_distance"))
            continue
        if cand_py and _HAS_PYPINYIN:
            name_py = to_pinyin(name)
            if cand_py == name_py:
                results.append((info, 50, "pinyin"))
    return results
