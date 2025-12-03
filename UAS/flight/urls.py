from django.urls import path
from . import views

urlpatterns = [
    path("", views.search_flight, name="search_flight"),
    path("results/", views.flight_results, name="flight_results"),
    path("booking/<str:flight_id>/", views.flight_booking, name="flight_booking"),
]
