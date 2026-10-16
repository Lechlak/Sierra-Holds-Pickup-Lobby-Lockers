"""Web app: choose a location, pull a title/item/INN-Reach paging list, reprint slips."""

import csv
import io

from dotenv import load_dotenv
from flask import Flask, Response, abort, render_template, request

from . import queries

CSV_COLUMNS = [
    "call_number", "volume", "title", "author", "barcode", "item_record_num",
    "item_location", "pickup_location_code", "ir_pickup_location_code",
    "ir_print_name", "patron_name", "patron_barcode", "placed_gmt", "hold_note",
]


def create_app(connect=queries.connect):
    load_dotenv()
    app = Flask(__name__)

    def pull(location, list_type):
        if list_type not in queries.LIST_TYPES or not location:
            abort(400)
        with connect() as conn:
            return queries.get_paging_list(conn, location, list_type)

    @app.get("/")
    def index():
        with connect() as conn:
            locations = queries.get_locations(conn)
        return render_template("index.html", locations=locations,
                               list_types=queries.LIST_TYPES)

    @app.get("/list")
    def paging_list():
        location = request.args.get("location", "")
        list_type = request.args.get("type", "")
        rows = pull(location, list_type)
        return render_template("list.html", rows=rows, location=location,
                               list_type=list_type,
                               list_label=queries.LIST_TYPES[list_type])

    @app.get("/slips")
    def slips():
        location = request.args.get("location", "")
        list_type = request.args.get("type", "")
        rows = pull(location, list_type)
        selected = set(request.args.getlist("hold"))
        if selected:
            rows = [r for r in rows if str(r["hold_id"]) in selected]
        return render_template("slips.html", rows=rows, list_type=list_type,
                               list_label=queries.LIST_TYPES[list_type])

    @app.get("/list.csv")
    def paging_csv():
        location = request.args.get("location", "")
        list_type = request.args.get("type", "")
        rows = pull(location, list_type)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        name = f"paging-{location}-{list_type}.csv"
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={name}"})

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
