import json

from bunker.ingest.parsers import get_parser, resolve_parser


def test_resolve_parser_by_id_field() -> None:
    source = {"id": "open_meteo_demo", "format": "json"}
    payload = json.dumps({"hourly": {"time": [], "temperature_2m": []}}).encode()
    rows = resolve_parser(source)(payload)
    assert rows == []


def test_usgs_parser_sets_feature_id() -> None:
    payload = {
        "features": [
            {
                "id": "abc",
                "properties": {"mag": 1.0},
                "geometry": {"coordinates": [1, 2, 3]},
            }
        ]
    }
    rows = get_parser("usgs_earthquakes_day")(json.dumps(payload).encode())
    assert rows[0]["_feature_id"] == "abc"