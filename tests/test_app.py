from contextlib import contextmanager
from datetime import datetime

import pytest

from paging_slips import app as app_module, queries

ROW = {
    "hold_id": 7, "placed_gmt": datetime(2026, 10, 1), "pickup_location_code": "mn",
    "ir_pickup_location_code": "ab123", "ir_print_name": "Other Univ", "hold_note": None,
    "item_record_num": "i1000001", "bib_record_num": "b100001", "barcode": "3100000001",
    "item_location": "mnst", "call_number": "QA76.73 .P98", "volume": None,
    "title": "Python basics", "author": "Doe, Jane", "patron_record_num": "p100001",
    "patron_barcode": "2100000001", "patron_name": "Smith, Pat",
}


@pytest.fixture
def client(monkeypatch):
    calls = []
    monkeypatch.setattr(queries, "get_locations", lambda conn: [{"code": "mnst", "name": "Main Stacks"}])

    def fake_list(conn, location, list_type):
        calls.append((location, list_type))
        return [ROW, {**ROW, "hold_id": 8, "title": "Other book"}]

    monkeypatch.setattr(queries, "get_paging_list", fake_list)

    @contextmanager
    def connect():
        yield object()

    flask_app = app_module.create_app(connect=connect)
    flask_app.config["TESTING"] = True
    c = flask_app.test_client()
    c.calls = calls
    return c


def test_index_lists_locations_and_types(client):
    html = client.get("/").get_data(as_text=True)
    assert "Main Stacks" in html
    for label in queries.LIST_TYPES.values():
        assert label in html


@pytest.mark.parametrize("list_type", ["title", "item", "innreach"])
def test_list_pulls_each_type(client, list_type):
    resp = client.get(f"/list?location=mn&type={list_type}")
    assert resp.status_code == 200
    assert "QA76.73 .P98" in resp.get_data(as_text=True)
    assert client.calls[-1] == ("mn", list_type)


def test_bad_type_rejected(client):
    assert client.get("/list?location=mn&type=bogus").status_code == 400


def test_slips_filter_to_checked_holds(client):
    html = client.get("/slips?location=mn&type=item&hold=8").get_data(as_text=True)
    assert "Other book" in html and "Python basics" not in html


def test_innreach_slip_shows_requesting_site(client):
    html = client.get("/slips?location=mn&type=innreach").get_data(as_text=True)
    assert "Other Univ" in html and "Smith, Pat" not in html


def test_csv_export(client):
    resp = client.get("/list.csv?location=mn&type=title")
    body = resp.get_data(as_text=True)
    assert resp.mimetype == "text/csv"
    assert body.splitlines()[0].startswith("call_number,")
    assert "3100000001" in body
