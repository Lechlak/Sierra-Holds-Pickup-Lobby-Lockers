# Sierra paging slip reprints

A small web app for reprinting Sierra paging slips. Pick a location, choose a
list, and print slips for all or only the checked holds.

| List | What it pulls |
|------|---------------|
| Title-level holds | Unfilled bib-level holds with an available item at the location (first item by call number is suggested) |
| Item-level holds | Unfilled item-level holds whose item is available at the location |
| INN-Reach requests | Unfilled INN-Reach requests (`hold.is_ir`) whose item is available at the location |

"Unfilled" means hold status `0` and not frozen. "Available" means item status
`-` and not checked out. The location field takes a full code or a prefix, so
`mn` covers `mnst`, `mnref`, and so on.

Data comes from Sierra Direct (the read-only `sierra_view` PostgreSQL schema),
because the Sierra REST API has no paging-list endpoint.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in your Sierra Direct host and SQL user
.venv/bin/flask --app paging_slips.app:create_app run
```

Then open http://127.0.0.1:5000.

The SQL user needs Sierra Direct access (Admin Corner → SQL access in the
Sierra admin app).

## Tests

```sh
.venv/bin/python -m pytest
```
