from datetime import timedelta
import mimetypes

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import HotelInformation
from apps.rooms.models import Room, RoomCategory
from .emails import (
    send_booking_approved_email,
    send_booking_confirmed_email,
    send_booking_pending_email,
    send_booking_rejected_email,
)
from .forms import (
    GuestBookingForm,
    PaymentProofUploadForm,
    ReceptionistApprovalForm,
    ReceptionistPaymentVerificationForm,
)
from .models import PaymentProof, PaymentVerificationStatus, Reservation, ReservationStatus
from .services import (
    approve_reservation_and_assign_room,
    confirm_reservation,
    create_guest_reservation,
    expire_overdue_reservations,
    reject_reservation,
    verify_payment_proof,
)


# ==============================================================================
# Public Guest Booking Workflow Views
# ==============================================================================

def booking_create_view(request, category_id=None):
    """
    Public booking request page. Guests choose a category, requested dates,
    and contact details. Physical rooms are never chosen by guests.
    """
    hotel_info = HotelInformation.get_solo()
    initial_category = None
    if category_id:
        initial_category = get_object_or_404(RoomCategory, pk=category_id, is_active=True)

    if request.method == 'POST':
        form = GuestBookingForm(request.POST, initial_category=initial_category)
        if form.is_valid():
            try:
                reservation = create_guest_reservation(
                    guest_name=form.cleaned_data['guest_name'],
                    email=form.cleaned_data['email'],
                    phone=form.cleaned_data['phone'],
                    room_category=form.cleaned_data['room_category'],
                    check_in=form.cleaned_data['check_in'],
                    check_out=form.cleaned_data['check_out'],
                    number_of_guests=form.cleaned_data['number_of_guests'],
                    special_requests=form.cleaned_data['special_requests'],
                )
                # Send acknowledgement email
                send_booking_pending_email(reservation, request=request)
                
                messages.success(
                    request,
                    _("Your booking request has been submitted successfully! Please review the details below.")
                )
                return redirect('reservations:booking_success', reference=reservation.reservation_reference)
            except ValidationError as e:
                form.add_error(None, e)
    else:
        form = GuestBookingForm(initial_category=initial_category)

    return render(request, 'reservations/booking_form.html', {
        'form': form,
        'initial_category': initial_category,
        'hotel_info': hotel_info,
    })


def booking_success_view(request, reference: str):
    """
    Public confirmation page shown immediately after a guest submits a booking request.
    Displays booking reference, guest stay summary, and explains the review process.
    """
    reservation = get_object_or_404(
        Reservation.objects.select_related('room_category', 'assigned_room'),
        reservation_reference=reference
    )
    hotel_info = HotelInformation.get_solo()

    return render(request, 'reservations/booking_success.html', {
        'reservation': reservation,
        'hotel_info': hotel_info,
    })


def payment_upload_view(request, token: str):
    """
    Guest page for viewing payment instructions and uploading transfer screenshots.
    Accessed exclusively through the secure, unguessable payment upload token.
    """
    # Clean up any overdue reservations first
    expire_overdue_reservations()

    reservation = get_object_or_404(
        Reservation.objects.select_related('room_category', 'assigned_room'),
        payment_upload_token=token
    )
    hotel_info = HotelInformation.get_solo()

    upload_form = None
    if reservation.status == ReservationStatus.AWAITING_PAYMENT and not reservation.is_payment_overdue:
        if request.method == 'POST':
            upload_form = PaymentProofUploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                proof = upload_form.save(commit=False)
                proof.reservation = reservation
                proof.verification_status = PaymentVerificationStatus.PENDING
                proof.save()

                messages.success(
                    request,
                    _("Payment screenshot uploaded successfully! Our front desk staff will verify your payment and issue your official confirmation.")
                )
                return redirect('reservations:payment_upload', token=token)
        else:
            upload_form = PaymentProofUploadForm()

    existing_proofs = reservation.payment_proofs.all().order_by('-uploaded_at')

    return render(request, 'reservations/payment_upload.html', {
        'reservation': reservation,
        'hotel_info': hotel_info,
        'upload_form': upload_form,
        'existing_proofs': existing_proofs,
    })


@staff_member_required
def protected_payment_proof_view(request, proof_id: int):
    """
    Serves payment proof screenshots exclusively to authenticated hotel staff.
    Unauthenticated or unauthorized access is denied.
    """
    if not request.user.is_staff:
        raise PermissionDenied("Access restricted to authorized hotel staff.")

    proof = get_object_or_404(PaymentProof, pk=proof_id)
    if not proof.screenshot:
        raise Http404("Payment proof document does not exist.")

    file_handle = proof.screenshot.open('rb')
    content_type, _ = mimetypes.guess_type(proof.screenshot.name)
    if not content_type:
        content_type = 'application/octet-stream'

    response = FileResponse(file_handle, content_type=content_type)
    filename = proof.screenshot.name.split('/')[-1]
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


# ==============================================================================
# Receptionist Workflow & Dashboard Views
# ==============================================================================

@staff_member_required
def reception_dashboard_view(request):
    """
    Receptionist dashboard overview.
    Displays counters, upcoming arrivals/departures, and reservations filtered by status.
    """
    expire_overdue_reservations()
    today = timezone.localdate()

    # Base queryset
    qs = Reservation.objects.select_related('room_category', 'assigned_room').order_by('-created_at')

    # Counters
    pending_count = qs.filter(status=ReservationStatus.PENDING_REVIEW).count()
    awaiting_count = qs.filter(status=ReservationStatus.AWAITING_PAYMENT).count()
    confirmed_count = qs.filter(status=ReservationStatus.CONFIRMED).count()
    today_arrivals_count = qs.filter(status=ReservationStatus.CONFIRMED, check_in=today).count()
    today_departures_count = qs.filter(status=ReservationStatus.CONFIRMED, check_out=today).count()

    # Filter logic
    status_filter = request.GET.get('status', 'pending_review')

    if status_filter == 'pending_review':
        reservations = qs.filter(status=ReservationStatus.PENDING_REVIEW)
    elif status_filter == 'awaiting_payment':
        reservations = qs.filter(status=ReservationStatus.AWAITING_PAYMENT)
    elif status_filter == 'confirmed':
        reservations = qs.filter(status=ReservationStatus.CONFIRMED)
    elif status_filter == 'today_arrivals':
        reservations = qs.filter(status=ReservationStatus.CONFIRMED, check_in=today)
    elif status_filter == 'today_departures':
        reservations = qs.filter(status=ReservationStatus.CONFIRMED, check_out=today)
    elif status_filter == 'all':
        reservations = qs
    else:
        reservations = qs.filter(status=status_filter)

    hotel_info = HotelInformation.get_solo()

    return render(request, 'reception/dashboard.html', {
        'reservations': reservations,
        'status_filter': status_filter,
        'pending_count': pending_count,
        'awaiting_count': awaiting_count,
        'confirmed_count': confirmed_count,
        'today_arrivals_count': today_arrivals_count,
        'today_departures_count': today_departures_count,
        'hotel_info': hotel_info,
        'today': today,
    })


@staff_member_required
def reception_reservation_detail_view(request, reservation_id: int):
    """
    Detailed receptionist management view for a specific reservation.
    Enables:
    - Approving and assigning physical rooms
    - Setting payment deadlines
    - Reviewing and verifying payment proof screenshots
    - Confirming or rejecting bookings
    """
    expire_overdue_reservations()

    reservation = get_object_or_404(
        Reservation.objects.select_related('room_category', 'assigned_room'),
        pk=reservation_id
    )

    approval_form = None
    if reservation.status == ReservationStatus.PENDING_REVIEW:
        approval_form = ReceptionistApprovalForm(reservation=reservation)

    payment_proofs = reservation.payment_proofs.select_related('verified_by').order_by('-uploaded_at')
    hotel_info = HotelInformation.get_solo()

    return render(request, 'reception/reservation_detail.html', {
        'reservation': reservation,
        'approval_form': approval_form,
        'payment_proofs': payment_proofs,
        'hotel_info': hotel_info,
    })


@staff_member_required
def reception_approve_reservation_view(request, reservation_id: int):
    """
    POST-only action: receptionist approves a pending reservation,
    assigns an operational physical room, sets payment deadline, and notifies guest.
    """
    if request.method != 'POST':
        return redirect('reservations:reception_detail', reservation_id=reservation_id)

    reservation = get_object_or_404(Reservation, pk=reservation_id)
    form = ReceptionistApprovalForm(reservation, request.POST)

    if form.is_valid():
        room = form.cleaned_data['assigned_room']
        deadline_hours = form.cleaned_data['deadline_hours']
        payment_deadline = timezone.now() + timedelta(hours=deadline_hours)

        try:
            approve_reservation_and_assign_room(
                reservation_id=reservation.pk,
                room_id=room.pk,
                staff_user=request.user,
                payment_deadline=payment_deadline,
            )
            reservation.refresh_from_db()
            send_booking_approved_email(reservation, request=request)

            messages.success(
                request,
                _(f"Reservation {reservation.reservation_reference} approved! "
                  f"Physical room {room.room_number} assigned. Payment link dispatched to {reservation.email}.")
            )
        except (ValidationError, PermissionDenied) as e:
            messages.error(request, str(e))
    else:
        messages.error(request, _("Please select a valid physical room from the available rooms list."))

    return redirect('reservations:reception_detail', reservation_id=reservation_id)


@staff_member_required
def reception_reject_reservation_view(request, reservation_id: int):
    """
    POST-only action: receptionist rejects a reservation request.
    """
    if request.method != 'POST':
        return redirect('reservations:reception_detail', reservation_id=reservation_id)

    reservation = get_object_or_404(Reservation, pk=reservation_id)
    reason = request.POST.get('rejection_reason', '').strip()

    try:
        reject_reservation(reservation_id=reservation.pk, staff_user=request.user, reason=reason)
        reservation.refresh_from_db()
        send_booking_rejected_email(reservation, reason=reason, request=request)

        messages.success(request, _(f"Reservation {reservation.reservation_reference} marked as rejected."))
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, str(e))

    return redirect('reservations:reception_dashboard')


@staff_member_required
def reception_verify_payment_view(request, proof_id: int):
    """
    POST-only action: receptionist reviews payment screenshot and marks it verified or rejected.
    """
    if request.method != 'POST':
        return redirect('reservations:reception_dashboard')

    proof = get_object_or_404(PaymentProof, pk=proof_id)
    status = request.POST.get('verification_status')
    notes = request.POST.get('verification_notes', '').strip()

    try:
        verify_payment_proof(
            proof_id=proof.pk,
            staff_user=request.user,
            status=status,
            notes=notes,
        )
        messages.success(
            request,
            _(f"Payment submission #{proof.pk} marked as {status.upper()}. "
              f"Remember to confirm the reservation once satisfied.")
        )
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, str(e))

    return redirect('reservations:reception_detail', reservation_id=proof.reservation_id)


@staff_member_required
def reception_confirm_reservation_view(request, reservation_id: int):
    """
    POST-only action: receptionist confirms an approved reservation once payment is verified.
    """
    if request.method != 'POST':
        return redirect('reservations:reception_detail', reservation_id=reservation_id)

    reservation = get_object_or_404(Reservation, pk=reservation_id)

    try:
        confirm_reservation(reservation_id=reservation.pk, staff_user=request.user)
        reservation.refresh_from_db()
        send_booking_confirmed_email(reservation, request=request)

        messages.success(
            request,
            _(f"Reservation {reservation.reservation_reference} is now CONFIRMED! Confirmation email dispatched to guest.")
        )
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, str(e))

    return redirect('reservations:reception_detail', reservation_id=reservation_id)
