"""Create the small, non-official demonstration SQLite snapshot in a chosen directory."""

import argparse
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    database = out / "example.sqlite"
    if database.exists():
        database.unlink()
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE experiments (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE measurements (
            id INTEGER PRIMARY KEY,
            experiment_id INTEGER NOT NULL REFERENCES experiments(id),
            value REAL NOT NULL,
            concentration REAL,
            concentration_unit TEXT,
            note TEXT
        );
        INSERT INTO experiments VALUES (1, 'Control'), (2, 'Treated');
        INSERT INTO measurements VALUES
            (1, 1, 1.5, 1000.0, 'uM', 'A'),
            (2, 1, 2.5, 2000.0, 'uM', NULL),
            (3, 2, 3.0, 1.0, 'mM', 'B'),
            (4, 2, 4.0, 2.0, 'mM', 'B');
    """)
    connection.close()
    print(database)


if __name__ == "__main__":
    main()
