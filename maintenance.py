"""Offline maintenance for persistent InterviewMirror database."""
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from storage import SQLiteStore


def main():
    parser = argparse.ArgumentParser(description='InterviewMirror offline database maintenance')
    parser.add_argument('--cleanup', action='store_true')
    args = parser.parse_args()
    if not args.cleanup:
        parser.error('No operation requested; use --cleanup')
    root = Path(__file__).resolve().parent
    load_dotenv(root / '.env')
    store = SQLiteStore(os.getenv('IM_DATABASE_PATH', str(root / '.data' / 'interviewmirror.sqlite3')))
    print(store.cleanup())

if __name__ == '__main__':
    main()
