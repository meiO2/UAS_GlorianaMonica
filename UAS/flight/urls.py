from django.urls import path
from . import views

urlpatterns = [
    path("", views.search_flight, name="search_flight"),
    path("results/", views.flight_results, name="flight_results"),
    path("return/<str:departure_flight_id>/", views.return_flights, name="return_flights"),
    path("booking/<str:flight_id>/", views.flight_booking, name="flight_booking"),
    path("booking/<str:departure_flight_id>/<str:return_flight_id>/", views.round_trip_booking, name="round_trip_booking"),
]
