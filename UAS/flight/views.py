import requests
from django.shortcuts import render
from django.conf import settings
from datetime import datetime


# =====================================
# 1) Get Access Token
# =====================================
def get_access_token():
    url = "https://test.api.amadeus.com/v1/security/oauth2/token"

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.AMADEUS_API_KEY,
        "client_secret": settings.AMADEUS_API_SECRET,
    }

    res = requests.post(url, headers=headers, data=data).json()
    return res.get("access_token")


# =====================================
# 2) City → IATA via API
# =====================================
def get_iata(city):
    token = get_access_token()
    if not token:
        return None

    url = "https://test.api.amadeus.com/v1/reference-data/locations"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"keyword": city, "subType": "AIRPORT"}

    r = requests.get(url, headers=headers, params=params).json()

    try:
        return r["data"][0]["iataCode"]
    except:
        return None


# =====================================
# Format Helpers
# =====================================
def format_datetime(dt_str):
    """2025-12-18T10:20:00 → 10:20, 18 Dec 2025"""
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%H:%M, %d %b %Y")
    except:
        return dt_str


def format_duration(iso_duration):
    """PT7H45M → 7h 45m"""
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
# 4) Flight Results (FORMATTED)
# =====================================
def flight_results(request):

    origin_city = request.GET.get("origin")
    destination_city = request.GET.get("destination")
    date = request.GET.get("departure_date")

    origin = get_iata(origin_city)
    destination = get_iata(destination_city)

    if not origin or not destination:
        return render(request, "flight_results.html", {
            "flights": [],
            "error": "City not found in Amadeus (Test environment)."
        })

    token = get_access_token()
    if not token:
        return render(request, "flight_results.html", {
            "flights": [],
            "error": "Authentication failed."
        })

    url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "originLocationCode": origin,
        "destinationLocationCode": destination,
        "departureDate": date,
        "adults": 1,
        "max": 10,
    }

    res = requests.get(url, headers=headers, params=params).json()
    flights_raw = res.get("data", [])

    formatted_flights = []

    for f in flights_raw:
        try:
            segments = f["itineraries"][0]["segments"]

            formatted_flights.append({
                "id": f["id"],
                "airline": f["validatingAirlineCodes"][0],
                "origin": segments[0]["departure"]["iataCode"],
                "destination": segments[-1]["arrival"]["iataCode"],
                "departure_time": format_datetime(segments[0]["departure"]["at"]),
                "arrival_time": format_datetime(segments[-1]["arrival"]["at"]),
                "duration": format_duration(f["itineraries"][0]["duration"]),
                "stops": len(segments) - 1,
                "price": f["price"]["total"],
            })
        except:
            continue

    # SAVE for booking page
    request.session["flights"] = formatted_flights

    return render(request, "flight_results.html", {
        "flights": formatted_flights,
        "origin": origin,
        "destination": destination,
        "error": None if formatted_flights else "No flights found."
    })


# =====================================
# 5) Booking Page
# =====================================
def flight_booking(request, flight_id):

    flights = request.session.get("flights", [])
    flight_data = None

    for f in flights:
        if f["id"] == flight_id:
            flight_data = f
            break

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
