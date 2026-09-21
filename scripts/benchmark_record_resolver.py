"""Offline microbenchmark; never opens the database or sends Telegram messages."""
from pathlib import Path
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.record_resolver import RecordCatalog, resolve_record_command


def main():
    tracemalloc.start()
    players = [{'id': i, 'nickname': f'Player Number {i}'} for i in range(500)]
    levels = [{'level_id': i, 'level_name': f'Level Number {i}', 'creator': 'Creator', 'position': i + 1}
              for i in range(2000)]
    catalog = RecordCatalog(players, levels)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    commands = [
        '/r Player Number 42 Level Number 100',
        '/r Player Number 42: Level Number 100 = 60 | 40-100',
        '/r Player Number 42: Level Number 100, Level Number 200, Level Number 300, Level Number 400',
    ]
    iterations = 5000
    started = time.perf_counter()
    for i in range(iterations):
        resolve_record_command(commands[i % len(commands)], catalog)
    elapsed = time.perf_counter() - started
    print(f'500 players, 2000 levels; catalog + source data peak: {peak / 1024 / 1024:.2f} MiB')
    print(f'{iterations} commands: {elapsed:.3f}s; mean: {elapsed * 1000 / iterations:.3f}ms/command')


if __name__ == '__main__':
    main()
