from django.shortcuts import render, redirect
from django.conf import settings
from amadeus import Client, ResponseError

def search_flight(request):
    return render(request, 'search_flight.html')


def flight_results(request):
    origin = request.GET.get("origin")
    destination = request.GET.get("destination")
    date = request.GET.get("departure_date")

    amadeus = Client(
        client_id=settings.AMADEUS_API_KEY,
        client_secret=settings.AMADEUS_API_SECRET
    )

    try:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=destination,
            departureDate=date,
            adults=1
        )
        flights = response.data
    except ResponseError:
        flights = []

    return render(request, 'flight_results.html', {"flights": flights})


def flight_booking(request, flight_id):
    if request.method == "POST":
        fullname = request.POST.get("name")
        passport = request.POST.get("passport")
        return render(request, "booking_success.html", {"name": fullname, "passport": passport, "flight": flight_id})

    return render(request, "flight_booking.html", {"flight_id": flight_id})
