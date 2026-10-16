"""Sierra Direct (sierra_view) queries for locations and paging lists.

A paging list is the set of unfilled holds (status '0', not frozen) that can be
filled by an item currently on the shelf at the chosen location:

* title  - bib-level holds; one available item at the location is suggested
* item   - item-level holds on an available item at the location
* innreach - INN-Reach requests (hold.is_ir) on an available item at the location
"""

import os

import psycopg
from psycopg.rows import dict_row

LIST_TYPES = {
    "title": "Title-level holds",
    "item": "Item-level holds",
    "innreach": "INN-Reach requests",
}

# Strip MARC subfield delimiters (|a, |b ...) from varfield content and squeeze spaces.
_CLEAN = "btrim(regexp_replace(regexp_replace({}, '\\|[a-z0-9]', ' ', 'g'), '\\s+', ' ', 'g'))"

LOCATIONS_SQL = """
SELECT l.code, COALESCE(n.name, l.code) AS name
FROM sierra_view.location l
LEFT JOIN sierra_view.location_name n
       ON n.location_id = l.id AND n.iii_language_id = 1
ORDER BY l.code
"""

# Columns shared by every list. Expects aliases h (hold), i (item_record),
# irm (item record_metadata), b (bib_record) and ip (item_record_property).
_SELECT = f"""
    h.id AS hold_id,
    h.placed_gmt,
    h.pickup_location_code,
    h.ir_pickup_location_code,
    h.ir_print_name,
    h.note AS hold_note,
    'i' || irm.record_num AS item_record_num,
    'b' || brm.record_num AS bib_record_num,
    ip.barcode,
    i.location_code AS item_location,
    COALESCE(
        (SELECT {_CLEAN.format('v.field_content')} FROM sierra_view.varfield v
          WHERE v.record_id = i.id AND v.varfield_type_code = 'c'
          ORDER BY v.occ_num LIMIT 1),
        (SELECT {_CLEAN.format('v.field_content')} FROM sierra_view.varfield v
          WHERE v.record_id = b.id AND v.varfield_type_code = 'c'
          ORDER BY v.occ_num LIMIT 1)
    ) AS call_number,
    (SELECT {_CLEAN.format('v.field_content')} FROM sierra_view.varfield v
      WHERE v.record_id = i.id AND v.varfield_type_code = 'v'
      ORDER BY v.occ_num LIMIT 1) AS volume,
    bp.best_title AS title,
    bp.best_author AS author,
    'p' || prm.record_num AS patron_record_num,
    pp.barcode AS patron_barcode,
    COALESCE(pn.last_name || ', ' || pn.first_name, pn.last_name) AS patron_name
"""

# An item is pageable when it is available ('-'), at the location, and not checked out.
_AVAILABLE_AT_LOCATION = """
    i.item_status_code = '-'
    AND i.location_code LIKE %(loc_prefix)s
    AND NOT EXISTS (SELECT 1 FROM sierra_view.checkout c WHERE c.item_record_id = i.id)
"""

_PATRON_JOINS = """
JOIN sierra_view.record_metadata prm ON prm.id = h.patron_record_id
LEFT JOIN sierra_view.patron_record_fullname pn
       ON pn.patron_record_id = h.patron_record_id AND pn.display_order = 0
LEFT JOIN LATERAL (
    SELECT v.field_content AS barcode FROM sierra_view.varfield v
     WHERE v.record_id = h.patron_record_id AND v.varfield_type_code = 'b'
     ORDER BY v.occ_num LIMIT 1
) pp ON true
"""

_UNFILLED = "h.status = '0' AND NOT h.is_frozen"

ITEM_LEVEL_SQL = f"""
SELECT {_SELECT}
FROM sierra_view.hold h
JOIN sierra_view.item_record i ON i.id = h.record_id
JOIN sierra_view.record_metadata irm ON irm.id = i.id
JOIN sierra_view.item_record_property ip ON ip.item_record_id = i.id
JOIN sierra_view.bib_record_item_record_link bl ON bl.item_record_id = i.id
JOIN sierra_view.bib_record b ON b.id = bl.bib_record_id
JOIN sierra_view.record_metadata brm ON brm.id = b.id
JOIN sierra_view.bib_record_property bp ON bp.bib_record_id = b.id
{_PATRON_JOINS}
WHERE {_UNFILLED}
  AND h.is_ir = %(is_ir)s
  AND {_AVAILABLE_AT_LOCATION}
ORDER BY call_number, title, h.placed_gmt
"""

# Bib-level holds: suggest the first available item at the location (by call number)
# so each hold appears once, as on Sierra's own paging list.
TITLE_LEVEL_SQL = f"""
SELECT * FROM (
    SELECT DISTINCT ON (h.id) {_SELECT}
    FROM sierra_view.hold h
    JOIN sierra_view.bib_record b ON b.id = h.record_id
    JOIN sierra_view.record_metadata brm ON brm.id = b.id
    JOIN sierra_view.bib_record_property bp ON bp.bib_record_id = b.id
    JOIN sierra_view.bib_record_item_record_link bl ON bl.bib_record_id = b.id
    JOIN sierra_view.item_record i ON i.id = bl.item_record_id
    JOIN sierra_view.record_metadata irm ON irm.id = i.id
    JOIN sierra_view.item_record_property ip ON ip.item_record_id = i.id
    {_PATRON_JOINS}
    WHERE {_UNFILLED}
      AND NOT h.is_ir
      AND {_AVAILABLE_AT_LOCATION}
    ORDER BY h.id, ip.call_number_norm NULLS LAST, irm.record_num
) t
ORDER BY call_number, title, placed_gmt
"""


def connect():
    return psycopg.connect(
        host=os.environ["SIERRA_DB_HOST"],
        port=os.environ.get("SIERRA_DB_PORT", "1032"),
        dbname=os.environ.get("SIERRA_DB_NAME", "iii"),
        user=os.environ["SIERRA_DB_USER"],
        password=os.environ["SIERRA_DB_PASSWORD"],
        sslmode=os.environ.get("SIERRA_DB_SSLMODE", "require"),
        row_factory=dict_row,
    )


def get_locations(conn):
    with conn.cursor() as cur:
        cur.execute(LOCATIONS_SQL)
        return cur.fetchall()


def get_paging_list(conn, location, list_type):
    """Return paging-list rows for a location code (prefix match) and list type."""
    if list_type not in LIST_TYPES:
        raise ValueError(f"unknown list type: {list_type}")
    params = {"loc_prefix": location.strip().lower() + "%"}
    if list_type == "title":
        sql = TITLE_LEVEL_SQL
    else:
        sql = ITEM_LEVEL_SQL
        params["is_ir"] = list_type == "innreach"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
