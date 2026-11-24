from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

app_name = 'reservations'

urlpatterns = [
    # Public Guest Booking URLs
    path('book/', views.booking_create_view, name='book'),
    path('book/<int:category_id>/', views.booking_create_view, name='book_category'),
    path('success/<str:reference>/', views.booking_success_view, name='booking_success'),
    path('payment/<str:token>/', views.payment_upload_view, name='payment_upload'),
    
    # Protected Media Document URL (Staff only)
    path('payment-proofs/<int:proof_id>/document/', views.protected_payment_proof_view, name='payment_proof_document'),

    # Receptionist Workflow Portal (Staff only)
    path('reception/', views.reception_dashboard_view, name='reception_dashboard'),
    path('reception/reservation/<int:reservation_id>/', views.reception_reservation_detail_view, name='reception_detail'),
    path('reception/reservation/<int:reservation_id>/approve/', views.reception_approve_reservation_view, name='reception_approve'),
    path('reception/reservation/<int:reservation_id>/reject/', views.reception_reject_reservation_view, name='reception_reject'),
    path('reception/reservation/<int:reservation_id>/confirm/', views.reception_confirm_reservation_view, name='reception_confirm'),
    path('reception/payment-proof/<int:proof_id>/verify/', views.reception_verify_payment_view, name='reception_verify_payment'),
]
