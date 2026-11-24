from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from apps.core.models import HotelInformation


def _get_base_url(request=None):
    if request:
        return request.build_absolute_uri('/')[:-1]
    return getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')


def send_booking_pending_email(reservation, request=None):
    """
    Sends notification to guest that their booking request was submitted
    and is awaiting receptionist review.
    """
    hotel_info = HotelInformation.get_solo()
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'reservations@betedanielhotel.com')
    
    subject = f"Booking Request Received - {reservation.reservation_reference} | {hotel_info.hotel_name}"
    
    message = (
        f"Dear {reservation.guest_name},\n\n"
        f"Thank you for choosing {hotel_info.hotel_name}.\n\n"
        f"We have received your booking request for the {reservation.room_category.name}.\n"
        f"Booking Reference: {reservation.reservation_reference}\n"
        f"Check-in: {reservation.check_in}\n"
        f"Check-out: {reservation.check_out} ({reservation.total_nights} night{'s' if reservation.total_nights != 1 else ''})\n"
        f"Number of Guests: {reservation.number_of_guests}\n"
        f"Estimated Total: ${reservation.total_price}\n\n"
        f"Our front desk team is currently reviewing room availability for your stay. "
        f"As soon as a room is assigned and approved, you will receive an email with payment instructions "
        f"and your secure payment upload link.\n\n"
        f"Warm regards,\n"
        f"Front Desk & Reservations\n"
        f"{hotel_info.hotel_name}\n"
        f"Phone: {hotel_info.phone}\n"
        f"Email: {hotel_info.email}\n"
    )
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[reservation.email],
            fail_silently=True,
        )
    except Exception:
        pass


def send_booking_approved_email(reservation, request=None):
    """
    Sends notification to guest that their reservation was approved by staff,
    physical room has been assigned, and payment screenshot must be uploaded before deadline.
    """
    hotel_info = HotelInformation.get_solo()
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'reservations@betedanielhotel.com')
    
    base_url = _get_base_url(request)
    upload_path = reverse('reservations:payment_upload', kwargs={'token': reservation.payment_upload_token})
    payment_link = f"{base_url}{upload_path}"
    
    deadline_str = (
        reservation.payment_deadline.strftime("%Y-%m-%d %H:%M UTC")
        if reservation.payment_deadline else "Within 24 hours"
    )
    room_str = f"Room {reservation.assigned_room.room_number}" if reservation.assigned_room else "Assigned Upon Arrival"
    
    subject = f"Booking Approved: Action Required - {reservation.reservation_reference} | {hotel_info.hotel_name}"
    
    message = (
        f"Dear {reservation.guest_name},\n\n"
        f"Good news! Your booking request at {hotel_info.hotel_name} has been approved by our reception team.\n\n"
        f"RESERVATION DETAILS:\n"
        f"----------------------------------------\n"
        f"Reference: {reservation.reservation_reference}\n"
        f"Category: {reservation.room_category.name}\n"
        f"Assigned Room: {room_str}\n"
        f"Check-in: {reservation.check_in} (from {hotel_info.check_in_time})\n"
        f"Check-out: {reservation.check_out} (by {hotel_info.check_out_time})\n"
        f"Total Stay: {reservation.total_nights} night{'s' if reservation.total_nights != 1 else ''}\n"
        f"Total Amount Due: ${reservation.total_price}\n\n"
        f"PAYMENT INSTRUCTIONS:\n"
        f"----------------------------------------\n"
        f"To confirm your reservation, please complete a bank transfer or mobile deposit for the total amount:\n"
        f"Bank: Commercial Bank of Ethiopia (CBE)\n"
        f"Account Name: {hotel_info.hotel_name}\n"
        f"Account Number: 1000123456789\n"
        f"Reference to quote: {reservation.reservation_reference}\n\n"
        f"IMPORTANT: PAYMENT DEADLINE\n"
        f"Your assigned room is held until: {deadline_str}.\n"
        f"If payment proof is not received before this time, the room will be automatically released.\n\n"
        f"SECURE PAYMENT UPLOAD LINK:\n"
        f"Please upload your payment screenshot/receipt using this link:\n"
        f"{payment_link}\n\n"
        f"Once received, our front desk will verify your transfer and issue your final booking confirmation.\n\n"
        f"Warm regards,\n"
        f"Reservations Team\n"
        f"{hotel_info.hotel_name}\n"
        f"Phone: {hotel_info.phone}\n"
    )
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[reservation.email],
            fail_silently=True,
        )
    except Exception:
        pass


def send_booking_confirmed_email(reservation, request=None):
    """
    Sends final confirmation to guest after staff verifies payment screenshot.
    """
    hotel_info = HotelInformation.get_solo()
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'reservations@betedanielhotel.com')
    
    room_str = f"Room {reservation.assigned_room.room_number}" if reservation.assigned_room else "Confirmed"
    
    subject = f"Official Confirmation - {reservation.reservation_reference} | {hotel_info.hotel_name}"
    
    message = (
        f"Dear {reservation.guest_name},\n\n"
        f"We are pleased to inform you that your payment has been verified. Your stay at {hotel_info.hotel_name} is officially CONFIRMED!\n\n"
        f"CONFIRMED BOOKING DETAILS:\n"
        f"----------------------------------------\n"
        f"Booking Reference: {reservation.reservation_reference}\n"
        f"Room: {room_str} ({reservation.room_category.name})\n"
        f"Guest Name: {reservation.guest_name}\n"
        f"Number of Guests: {reservation.number_of_guests}\n"
        f"Check-in: {reservation.check_in} (from {hotel_info.check_in_time})\n"
        f"Check-out: {reservation.check_out} (by {hotel_info.check_out_time})\n"
        f"Duration: {reservation.total_nights} night{'s' if reservation.total_nights != 1 else ''}\n"
        f"Payment Status: VERIFIED & CONFIRMED\n\n"
        f"ARRIVAL INFORMATION:\n"
        f"----------------------------------------\n"
        f"Address: {hotel_info.address}\n"
        f"Front Desk: Open 24/7 ({hotel_info.reception_hours})\n"
        f"Contact Phone: {hotel_info.phone}\n"
        f"Please present your booking reference '{reservation.reservation_reference}' upon arrival.\n\n"
        f"We look forward to welcoming you to Addis Ababa.\n\n"
        f"Warm regards,\n"
        f"General Manager & Staff\n"
        f"{hotel_info.hotel_name}\n"
    )
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[reservation.email],
            fail_silently=True,
        )
    except Exception:
        pass


def send_booking_rejected_email(reservation, reason="", request=None):
    """
    Notifies guest if reservation request cannot be accommodated.
    """
    hotel_info = HotelInformation.get_solo()
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'reservations@betedanielhotel.com')
    
    subject = f"Update Regarding Booking Request - {reservation.reservation_reference} | {hotel_info.hotel_name}"
    
    reason_text = f"\nStaff Note: {reason}\n" if reason else ""
    
    message = (
        f"Dear {reservation.guest_name},\n\n"
        f"Thank you for your interest in staying at {hotel_info.hotel_name}.\n\n"
        f"Unfortunately, we are unable to accommodate your booking request ({reservation.reservation_reference}) "
        f"for the dates {reservation.check_in} to {reservation.check_out}.{reason_text}\n"
        f"If your travel schedule is flexible, we invite you to browse our room categories for alternative dates "
        f"or contact our reception directly.\n\n"
        f"Warm regards,\n"
        f"Reservations Team\n"
        f"{hotel_info.hotel_name}\n"
        f"Phone: {hotel_info.phone}\n"
        f"Email: {hotel_info.email}\n"
    )
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[reservation.email],
            fail_silently=True,
        )
    except Exception:
        pass
