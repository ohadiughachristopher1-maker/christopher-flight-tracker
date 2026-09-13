from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
import requests
import time
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

OPENSKY_URL = "https://opensky-network.org/api/states/all"

AIRLINES = {
    "APK": "Air Peace",
    "AEN": "Aero Contractors",
    "MEP": "Med-View Airline",
    "NGR": "Nigeria Air",
    "DAN": "Dana Air",
    "KQA": "Kenya Airways",
    "ETH": "Ethiopian Airlines",
    "RWD": "RwandAir",
    "BAW": "British Airways",
    "AFR": "Air France",
    "DLH": "Lufthansa",
    "KLM": "KLM",
    "BAW": "British Airways",
    "UAE": "Emirates",
    "QTR": "Qatar Airways",
    "ETD": "Etihad Airways",
    "THY": "Turkish Airlines",
    "AAL": "American Airlines",
    "UAL": "United Airlines",
    "DAL": "Delta Air Lines",
    "SIA": "Singapore Airlines",
    "CPA": "Cathay Pacific",
}

REGIONS = {
    "nigeria": {
        "lamin": 4.0,
        "lomin": 2.5,
        "lamax": 14.0,
        "lomax": 15.0
    },
    "africa": {
        "lamin": -35.0,
        "lomin": -20.0,
        "lamax": 38.0,
        "lomax": 55.0
    },
    "world": {}
}


def get_airline(callsign):
    if not callsign:
        return "Unknown airline"

    prefix = callsign.strip().split()[0][:3].upper()
    return AIRLINES.get(prefix, "Unknown airline")


def get_status(on_ground, vertical_rate):
    if on_ground:
        return "On ground"

    if vertical_rate is None:
        return "Cruising"

    if vertical_rate > 0.5:
        return "Climbing"

    if vertical_rate < -0.5:
        return "Descending"

    return "Cruising"


@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/api/health")
def health():
    return jsonify({
        "status": "online",
        "project": "Christopher Flight Tracker"
    })


@app.route("/api/flights")
def flights():
    region = request.args.get("region", "world").lower()

    params = REGIONS.get(region, REGIONS["world"])

    try:
        response = requests.get(
            OPENSKY_URL,
            params=params,
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

        aircraft = []

        for state in data.get("states") or []:
            if not state:
                continue

            callsign = (state[1] or "").strip()
            longitude = state[5]
            latitude = state[6]
            altitude = state[7]
            on_ground = state[8]
            velocity = state[9]
            heading = state[10]
            vertical_rate = state[11]

            if latitude is None or longitude is None:
                continue

            aircraft.append({
                "icao24": state[0],
                "callsign": callsign or "N/A",
                "origin_country": state[2] or "Unknown",
                "longitude": longitude,
                "latitude": latitude,
                "altitude_m": altitude,
                "altitude_ft": round(altitude * 3.28084) if altitude else None,
                "on_ground": bool(on_ground),
                "velocity_ms": velocity,
                "speed_knots": round(velocity * 1.94384) if velocity else None,
                "heading": heading,
                "vertical_rate_ms": vertical_rate,
                "vertical_rate_fpm": round(vertical_rate * 196.8504)
                    if vertical_rate is not None else None,
                "status": get_status(on_ground, vertical_rate),
                "airline": get_airline(callsign),
                "departure": state[2] or "Unknown",
                "destination": "Not available from live ADS-B data"
            })

        stats = {
            "total": len(aircraft),
            "climbing": sum(
                1 for a in aircraft if a["status"] == "Climbing"
            ),
            "descending": sum(
                1 for a in aircraft if a["status"] == "Descending"
            ),
            "cruising": sum(
                1 for a in aircraft if a["status"] == "Cruising"
            ),
            "on_ground": sum(
                1 for a in aircraft if a["status"] == "On ground"
            )
        }

        return jsonify({
            "success": True,
            "region": region,
            "timestamp": int(time.time()),
            "statistics": stats,
            "aircraft": aircraft
        })

    except Exception as e:
        return jsonify({
            "success": False,
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


@app.route("/api/route/<icao24>")
def route(icao24):
    try:
        icao24 = icao24.lower().strip()

        now = int(time.time())

        # Search the previous 24 hours.
        begin = now - 86400
        end = now

        url = "https://opensky-network.org/api/flights/aircraft"

        response = requests.get(
            url,
            params={
                "icao24": icao24,
                "begin": begin,
                "end": end
            },
            timeout=30
        )

        if response.status_code == 404:
            return jsonify({
                "success": True,
                "available": False,
                "message": "No route information is currently available."
            })

        response.raise_for_status()

        flights = response.json()

        if not flights:
            return jsonify({
                "success": True,
                "available": False,
                "message": "No route information is currently available."
            })

        # Use the most recent flight record.
        flight = flights[-1]

        departure = flight.get("estDepartureAirport")
        arrival = flight.get("estArrivalAirport")
        callsign = flight.get("callsign")

        return jsonify({
            "success": True,
            "available": bool(departure or arrival),
            "icao24": icao24,
            "callsign": callsign.strip() if callsign else None,
            "departure": departure,
            "arrival": arrival,
            "departure_candidates": flight.get(
                "departureAirportCandidatesCount"
            ),
            "arrival_candidates": flight.get(
                "arrivalAirportCandidatesCount"
            ),
            "message": (
                "Route information found."
                if departure or arrival
                else "Route information unavailable."
            )
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "available": False,
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
