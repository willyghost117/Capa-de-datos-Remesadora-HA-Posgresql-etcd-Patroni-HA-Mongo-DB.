from django.urls import path

from ha_api import views


urlpatterns = [
    path("", views.index, name="index"),
    path("health", views.health, name="health"),
    path("api/topology/", views.topology, name="topology"),
    path("api/remittance-trace/<uuid:event_id>/", views.remittance_trace, name="remittance_trace"),
    path("api/generator/insert-remittance/", views.insert_random_remittance, name="insert_random_remittance"),
    path("api/events/", views.events, name="events"),
]
