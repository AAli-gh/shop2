from django.urls import path

from apps.newsletter import views

app_name = "newsletter"

urlpatterns = [
    path("subscribe/", views.subscribe, name="subscribe"),
    path("verify/<str:token>/", views.verify, name="verify"),
    path("unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
]
