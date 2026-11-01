
from django.urls import path

from chatbot.views import ChatAPIView
from chatbot.booking_views import (
    BookingAvailabilityAPIView,
    BookingCreateAPIView,
    ClientProfileAPIView,
)

from chatbot.conversation_views import (
    ConversationMessageListAPIView,
    ConversationSessionListCreateAPIView,
)

urlpatterns = [
    path(
        "chat/",
        ChatAPIView.as_view(),
        name="chat",
    ),
    path(
        "clients/profile/",
        ClientProfileAPIView.as_view(),
        name="client-profile",
    ),
    path(
        "bookings/availability/",
        BookingAvailabilityAPIView.as_view(),
        name="booking-availability",
    ),
    path(
        "bookings/create/",
        BookingCreateAPIView.as_view(),
        name="booking-create",
    ),
    path("sessions/", ConversationSessionListCreateAPIView.as_view(), name="conversation-sessions"),
    path("sessions/<str:session_id>/messages/", ConversationMessageListAPIView.as_view(), name="conversation-messages"),

]
