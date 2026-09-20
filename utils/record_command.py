import shlex


def parse_progress(prog_str: str):
    prog_str = prog_str.replace('%', '')
    if '-' in prog_str:
        start, end = prog_str.split('-')
        return int(start), int(end)
    return 0, int(prog_str)


def parse_record_command(text: str):
    """Return the nickname and (level query, start, end) actions.

    Unquoted commas separate full completions. Quoted commas belong to names.
    Without separators, preserve the single-level progress/run syntax.
    """
    lexer = shlex.shlex(text, posix=True, punctuation_chars=',')
    lexer.whitespace_split = True
    lexer.commenters = ''
    args = list(lexer)
    if len(args) < 3:
        raise ValueError('Укажите ник игрока и хотя бы один уровень.')

    nick = args[1]
    level_args = args[2:]
    if any(token and set(token) == {','} for token in level_args):
        levels = []
        current = []
        for token in level_args:
            if token and set(token) == {','}:
                name = ' '.join(current).strip()
                if token != ',' or not name:
                    raise ValueError('Между запятыми должно быть название уровня.')
                levels.append(name)
                current = []
            else:
                current.append(token)
        name = ' '.join(current).strip()
        if not name:
            raise ValueError('После запятой должно быть название уровня.')
        levels.append(name)

        # Avoid writing and notifying twice for repeated names in one command.
        seen = set()
        actions = []
        for name in levels:
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                actions.append((name, 0, 100))
        return nick, actions

    level_query = level_args[0]
    progress_str = ' '.join(level_args[1:]) or '100'
    progresses = [parse_progress(p.strip()) for p in progress_str.split('|') if p.strip()]
    return nick, [(level_query, start, end) for start, end in progresses or [(0, 100)]]
