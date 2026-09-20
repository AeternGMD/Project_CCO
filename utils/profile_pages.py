def split_profile_text(text: str, limit: int = 3800) -> list[str]:
    """Keep all text, splitting on lines within a conservative UTF-16 budget.

    Leave room for a page footer within Telegram's 4096-character limit.
    Even a single oversized line is split without dropping any characters.
    """
    pages = []
    current = ""
    current_size = 0
    for line in text.splitlines(keepends=True):
        line_size = len(line.encode("utf-16-le")) // 2
        if current and current_size + line_size > limit:
            pages.append(current)
            current = ""
            current_size = 0
        if line_size <= limit:
            current += line
            current_size += line_size
            continue

        for char in line:
            char_size = 2 if ord(char) > 0xFFFF else 1
            if current_size + char_size > limit:
                pages.append(current)
                current = ""
                current_size = 0
            current += char
            current_size += char_size

    if current:
        pages.append(current)
    return pages or [""]
