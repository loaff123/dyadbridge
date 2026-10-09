"""Read generated CSV with explicit bounded field/stream limits.

Large run metadata can exceed Python csv's default 128KiB field limit and
spreadsheet cell limits. JSONL is the primary full-fidelity interchange format.
"""
import argparse
from contextlib import contextmanager
import csv

RECORD_BYTES=8388608
STREAM_BYTES=268435456
MAX_ROWS=1010003  # CSV header plus run/sample/event/completion records.


def _bounded_lines(source):
    total=0;rows=0
    while True:
        raw=source.readline(RECORD_BYTES+1)
        if not raw:return
        total+=len(raw);rows+=1
        if len(raw)>RECORD_BYTES or total>STREAM_BYTES or rows>MAX_ROWS:
            raise ValueError('CSV export envelope exceeded')
        if not raw.endswith(b'\n'):raise ValueError('Incomplete CSV line')
        yield raw.decode('utf-8')


@contextmanager
def event_rows(path):
    previous=csv.field_size_limit(RECORD_BYTES)
    try:
        with open(path,'rb') as source:
            reader=csv.DictReader(_bounded_lines(source))
            yield (row for row in reader if row['record_type']=='event')
    finally:
        csv.field_size_limit(previous)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('csv_file');args=parser.parse_args()
    with event_rows(args.csv_file) as rows:
        count=sum(1 for _ in rows)
    print(count,'real event rows; metadata field limit restored')
