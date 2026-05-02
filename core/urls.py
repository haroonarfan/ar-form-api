from django.urls import path
from contact.views import submit

urlpatterns = [
    path('contact/', submit),
]