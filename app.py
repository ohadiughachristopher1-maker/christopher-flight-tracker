from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import requests
import time

app = Flask(__name__)
CORS(app)

ADSB_URL = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist}"

REGIONS = {
    "nigeria": {
        "lat": 9.08,
        "lon": 8.67,
        "dist": 600
    },
    "africa": {
        "lat": 5.0,
        "lon": 20.0,
        "dist": 2500
    },
    "world": {
        "lat": 20.0,
        "lon": 0.0,
        "dist": 5000
    }
}


def get_status(on_ground, vertical_rate):
    if on_ground:
        return "On ground"

    if vertical_rate is None:
        return "Cruising"

    if vertical_rate > 100:
        return "Climbing"

    if vertical_rate < -100:
        return "Descending"

    return "Cruising"


def clean_callsign(value):
    if not value:
        return "N/A"
    return value.strip()


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/api/health")
def health():
    return jsonify({
        "status": "online",
        "project": "Christopher Flight Tracker",
        "data_source": "ADSB.lol"
    })


@app.route("/api/flights")
def flights():
    region = request.args.get("region", "world").lower()

    if region not in REGIONS:
        region = "world"

    settings = REGIONS[region]

    try:
        url = ADSB_URL.format(
            lat=settings["lat"],
            lon=settings["lon"],
            dist=settings["dist"]
        )

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()

        aircraft = []

        for state in data.get("ac", []):
            latitude = state.get("lat")
            longitude = state.get("lon")

            if latitude is None or longitude is None:
                continue

            callsign = clean_callsign(state.get("flight"))

            altitude = state.get("alt_baro")
            speed = state.get("gs")
            vertical_rate = state.get("baro_rate")
            heading = state.get("track")

            on_ground = (
                altitude == "ground"
                or state.get("ground") is True
            )

            if isinstance(altitude, str):
                altitude_ft = None
                altitude_m = None
            else:
                altitude_ft = round(altitude) if altitude is not None else None
                altitude_m = (
                    round(altitude * 0.3048)
                    if altitude is not None
                    else None
                )

            aircraft.append({
                "icao24": state.get("hex", "").lower(),
                "callsign": callsign,
                "registration": state.get("r", "Unknown"),
                "aircraft_type": state.get("t", "Unknown"),
                "origin_country": "Unknown",
                "longitude": longitude,
                "latitude": latitude,
                "altitude_ft": altitude_ft,
                "altitude_m": altitude_m,
                "speed_knots": round(speed) if speed is not None else None,
                "heading": round(heading, 1) if heading is not None else None,
                "vertical_rate_fpm": (
                    round(vertical_rate)
                    if vertical_rate is not None
                    else None
                ),
                "status": get_status(
                    on_ground,
                    vertical_rate
                ),
                "airline": callsign[:3] if callsign != "N/A" else "Unknown",
                "departure": "Not available",
                "destination": "Not available"
            })

        stats = {
            "total": len(aircraft),
            "climbing": sum(
                1 for a in aircraft
                if a["status"] == "Climbing"
            ),
            "descending": sum(
                1 for a in aircraft
                if a["status"] == "Descending"
            ),
            "cruising": sum(
                1 for a in aircraft
                if a["status"] == "Cruising"
            ),
            "on_ground": sum(
                1 for a in aircraft
                if a["status"] == "On ground"
            )
        }

        return jsonify({
            "success": True,
            "source": "ADSB.lol",
            "region": region,
            "timestamp": int(time.time()),
            "statistics": stats,
            "aircraft": aircraft
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "source": "ADSB.lol",
            "error": str(e),
            "statistics": {
                "total": 0,
                "climbing": 0,
                "descending": 0,
                "cruising": 0,
                "on_ground": 0
            },
            "aircraft": []
        }), 500


@app.route("/api/aircraft/<icao24>")
def aircraft_details(icao24):
    try:
        icao24 = icao24.lower().strip()

        url = "https://api.adsb.lol/v2/hex/" + icao24

        response = requests.get(
            url,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        aircraft = data.get("ac", [])

        if not aircraft:
            return jsonify({
                "success": False,
                "message": "Aircraft not found"
            }), 404

        plane = aircraft[0]

        return jsonify({
            "success": True,
            "aircraft": plane
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
