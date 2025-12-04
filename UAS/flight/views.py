import logging
import requests
from django.shortcuts import render, redirect
from django.conf import settings
from datetime import datetime, timedelta

# =====================================
# Logger Setup
# =====================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# =====================================
# Global cache (in-memory, simple)
# =====================================
TOKEN_CACHE = {"token": None, "expires_at": None}
IATA_CACHE = {}

# =====================================
# 1) Get Access Token (Cached)
# =====================================
def get_access_token():
    now = datetime.utcnow()
    if TOKEN_CACHE["token"] and TOKEN_CACHE["expires_at"] > now:
        return TOKEN_CACHE["token"]

    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.AMADEUS_API_KEY,
        "client_secret": settings.AMADEUS_API_SECRET,
    }

    try:
        res = requests.post(url, headers=headers, data=data, timeout=10).json()
        token = res.get("access_token")
        expires_in = res.get("expires_in", 1800)

        if token:
            TOKEN_CACHE["token"] = token
            TOKEN_CACHE["expires_at"] = now + timedelta(seconds=expires_in - 30)
            logger.info("Access token retrieved successfully.")
            return token
        else:
            logger.error(f"Failed to get access token: {res}")
            return None
    except Exception as e:
        logger.error(f"Error getting access token: {e}")
        return None

# =====================================
# 2) City → IATA via API (Cached)
# =====================================
def get_iata(city):
    city_key = city.lower()
    if city_key in IATA_CACHE:
        return IATA_CACHE[city_key]

    token = get_access_token()
    if not token:
        return None

    url = "https://test.api.amadeus.com/v1/reference-data/locations"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"keyword": city, "subType": "AIRPORT"}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=5).json()
        code = r["data"][0]["iataCode"]
        IATA_CACHE[city_key] = code
        logger.info(f"IATA code for {city}: {code}")
        return code
    except Exception as e:
        logger.error(f"Error getting IATA for {city}: {e}")
        return None

# =====================================
# Format Helpers
# =====================================
def format_datetime(dt_str):
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%H:%M, %d %b %Y")
    except:
        return dt_str

def format_duration(iso_duration):
    if not iso_duration:
        return ""
    hours = ""
    minutes = ""
    if "H" in iso_duration:
        hours = iso_duration.split("T")[1].split("H")[0] + "h "
    if "M" in iso_duration:
        minutes = iso_duration.split("H")[-1].replace("M", "") + "m"
    return (hours + minutes).strip()

# =====================================
# 3) Search Page
# =====================================
def search_flight(request):
    return render(request, "search_flight.html")

# =====================================
# 4) Flight Results (Departure flights)
# =====================================
def flight_results(request):
    origin_city = request.GET.get("origin")
    destination_city = request.GET.get("destination")
    departure_date = request.GET.get("departure_date")
    return_date = request.GET.get("return_date")

    origin = get_iata(origin_city)
    destination = get_iata(destination_city)

    if not origin or not destination:
        return render(request, "flight_results.html", {
            "departure_flights": [],
            "is_round_trip": bool(return_date),
            "error": "City not found in Amadeus."
        })

    token = get_access_token()
    if not token:
        return render(request, "flight_results.html", {
            "departure_flights": [],
            "is_round_trip": bool(return_date),
            "error": "Authentication failed."
        })

    def fetch_flights(origin_code, dest_code, date):
        if not date or not date.strip():
            return []

        url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "originLocationCode": origin_code,
            "destinationLocationCode": dest_code,
            "departureDate": date,
            "adults": 1,
            "max": 10,
        }
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10).json()
            flights_raw = res.get("data", [])
            logger.info(f"Fetched {len(flights_raw)} raw flights for {origin_code} → {dest_code} on {date}")
        except Exception as e:
            logger.error(f"Error fetching flights for {origin_code} → {dest_code} on {date}: {e}")
            flights_raw = []

        formatted = []
        for f in flights_raw:
            try:
                segments = f["itineraries"][0]["segments"]
                formatted.append({
                    "id": f["id"],
                    "airline": f["validatingAirlineCodes"][0],
                    "origin": segments[0]["departure"]["iataCode"],
                    "destination": segments[-1]["arrival"]["iataCode"],
                    "departure_time": format_datetime(segments[0]["departure"]["at"]),
                    "arrival_time": format_datetime(segments[-1]["arrival"]["at"]),
                    "duration": format_duration(f["itineraries"][0]["duration"]),
                    "stops": len(segments) - 1,
                    "price": "%.2f" % float(f["price"]["total"]),
                })
            except:
                continue
        return formatted

    departure_flights = fetch_flights(origin, destination, departure_date)

    request.session["search_params"] = {
        "origin_city": origin_city,
        "destination_city": destination_city,
        "departure_date": departure_date,
        "return_date": return_date,
        "origin": origin,
        "destination": destination,
    }
    request.session["departure_flights"] = departure_flights

    return render(request, "flight_results.html", {
        "departure_flights": departure_flights,
        "is_round_trip": bool(return_date),
        "error": None if departure_flights else "No flights found."
    })

# =====================================
# 5) Return Flights (Round-trip)
# =====================================
def return_flights(request, departure_flight_id):
    search_params = request.session.get("search_params", {})
    return_date = search_params.get("return_date")

    if not return_date:
        return redirect("flight_booking", flight_id=departure_flight_id)

    origin = search_params.get("destination")
    destination = search_params.get("origin")
    token = get_access_token()
    if not token:
        return render(request, "return_flights.html", {
            "return_flights": [],
            "departure_flight_id": departure_flight_id,
            "error": "Authentication failed."
        })

    def fetch_flights(origin_code, dest_code, date):
        if not date or not date.strip():
            return []

        url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "originLocationCode": origin_code,
            "destinationLocationCode": dest_code,
            "departureDate": date,
            "adults": 1,
            "max": 10,
        }
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10).json()
            flights_raw = res.get("data", [])
            logger.info(f"Fetched {len(flights_raw)} raw return flights for {origin_code} → {dest_code} on {date}")
        except Exception as e:
            logger.error(f"Error fetching return flights for {origin_code} → {dest_code} on {date}: {e}")
            flights_raw = []

        formatted = []
        for f in flights_raw:
            try:
                segments = f["itineraries"][0]["segments"]
                formatted.append({
                    "id": f["id"],
                    "airline": f["validatingAirlineCodes"][0],
                    "origin": segments[0]["departure"]["iataCode"],
                    "destination": segments[-1]["arrival"]["iataCode"],
                    "departure_time": format_datetime(segments[0]["departure"]["at"]),
                    "arrival_time": format_datetime(segments[-1]["arrival"]["at"]),
                    "duration": format_duration(f["itineraries"][0]["duration"]),
                    "stops": len(segments) - 1,
                    "price": "%.2f" % float(f["price"]["total"]),
                })
            except:
                continue
        return formatted

    return_flights_list = fetch_flights(origin, destination, return_date)
    request.session["return_flights"] = return_flights_list

    return render(request, "return_flights.html", {
        "return_flights": return_flights_list,
        "departure_flight_id": departure_flight_id,
        "error": None if return_flights_list else "No return flights found."
    })

# =====================================
# 6) Booking Page (One-way)
# =====================================
def flight_booking(request, flight_id):
    departure_flights = request.session.get("departure_flights", [])
    return_flights = request.session.get("return_flights", [])
    all_flights = departure_flights + return_flights

    flight_data = next((f for f in all_flights if f["id"] == flight_id), None)

    if request.method == "POST":
        return render(request, "booking_success.html", {
            "name": request.POST.get("name"),
            "passport": request.POST.get("passport"),
            "flight": flight_data,
        })

    return render(request, "flight_booking.html", {
        "flight": flight_data,
        "flight_id": flight_id
    })

# =====================================
# 7) Round-Trip Booking Page
# =====================================
def round_trip_booking(request, departure_flight_id, return_flight_id):
    departure_flights = request.session.get("departure_flights", [])
    return_flights = request.session.get("return_flights", [])

    departure_flight = next((f for f in departure_flights if f["id"] == departure_flight_id), None)
    return_flight = next((f for f in return_flights if f["id"] == return_flight_id), None)

    total_price = None
    if departure_flight and return_flight:
        total_price = "%.2f" % (float(departure_flight["price"]) + float(return_flight["price"]))

    if request.method == "POST":
        return render(request, "booking_success.html", {
            "name": request.POST.get("name"),
            "passport": request.POST.get("passport"),
            "departure_flight": departure_flight,
            "return_flight": return_flight,
            "total_price": total_price,
        })

    return render(request, "round_trip_booking.html", {
        "departure_flight": departure_flight,
        "return_flight": return_flight,
        "total_price": total_price,
        "departure_flight_id": departure_flight_id,
        "return_flight_id": return_flight_id,
    })
