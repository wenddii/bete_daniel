from datetime import date, datetime, timedelta
from typing import List, Optional

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.rooms.models import Room, RoomCategory, RoomOperationalStatus
from .models import PaymentProof, PaymentVerificationStatus, Reservation, ReservationStatus


@transaction.atomic
def expire_overdue_reservations() -> int:
    """
    Finds all reservations in 'awaiting_payment' status whose payment deadline has passed,
    marks them as 'expired', and releases their assigned room.
    Uses select_for_update() to prevent race conditions.
    Returns the count of expired reservations.
    """
    now = timezone.now()
    overdue = Reservation.objects.select_for_update().filter(
        status=ReservationStatus.AWAITING_PAYMENT,
        payment_deadline__isnull=False,
        payment_deadline__lt=now,
    )

    count = 0
    for res in overdue:
        res.status = ReservationStatus.EXPIRED
        res.assigned_room = None
        res.save(update_fields=['status', 'assigned_room', 'updated_at'])
        count += 1

    return count


def get_category_available_rooms(
    category: RoomCategory,
    check_in: date,
    check_out: date,
    exclude_reservation_id: Optional[int] = None
) -> QuerySet[Room]:
    """
    Returns the queryset of physical rooms in the given category that:
    1. Have operational_status == ACTIVE
    2. Have NO overlapping active/blocking reservation (awaiting_payment or confirmed)
       between check_in and check_out.

    Note: Expired reservations are automatically released.
    """
    if check_out <= check_in:
        raise ValidationError(_("Check-out date must be strictly after check-in date."))

    # First synchronize expired reservations so overdue rooms are released
    expire_overdue_reservations()

    # Active physical rooms belonging to this category
    active_rooms = Room.objects.filter(
        category=category,
        operational_status=RoomOperationalStatus.ACTIVE,
    )

    # Find rooms that currently have overlapping blocking reservations
    now = timezone.now()
    blocking_query = Reservation.objects.filter(
        assigned_room__in=active_rooms,
        check_in__lt=check_out,
        check_out__gt=check_in,
    ).filter(
        # Confirmed always blocks
        # Awaiting payment blocks only if deadline is not passed
        models_q := (
            (models.Q(status=ReservationStatus.CONFIRMED)) |
            (models.Q(status=ReservationStatus.AWAITING_PAYMENT) & (
                models.Q(payment_deadline__isnull=True) | models.Q(payment_deadline__gt=now)
            ))
        )
    )

    if exclude_reservation_id:
        blocking_query = blocking_query.exclude(pk=exclude_reservation_id)

    blocked_room_ids = blocking_query.values_list('assigned_room_id', flat=True).distinct()

    return active_rooms.exclude(id__in=blocked_room_ids)


from django.db import models


def check_category_availability(
    category: RoomCategory,
    check_in: date,
    check_out: date
) -> int:
    """
    Returns the number of available physical rooms for the category and date range.
    """
    if not category.is_active:
        return 0
    return get_category_available_rooms(category, check_in, check_out).count()


@transaction.atomic
def create_guest_reservation(
    *,
    guest_name: str,
    email: str,
    phone: str,
    room_category: RoomCategory,
    check_in: date,
    check_out: date,
    number_of_guests: int,
    special_requests: str = "",
) -> Reservation:
    """
    Creates a new reservation request submitted by a guest.
    Guarantees:
    - Guests select room categories, NEVER individual room numbers.
    - Validates server-side availability for the room category.
    - Created with status 'pending_review' and NO assigned room.
    - Pending requests do NOT consume room capacity.
    """
    if not room_category.is_active:
        raise ValidationError(_("Selected room category is not currently available for booking."))

    if check_in < timezone.localdate():
        raise ValidationError(_("Check-in date cannot be in the past."))

    if check_out <= check_in:
        raise ValidationError(_("Check-out date must be strictly after check-in date."))

    if number_of_guests < 1:
        raise ValidationError(_("At least one guest is required."))

    if number_of_guests > room_category.capacity:
        raise ValidationError(
            _(f"Requested number of guests ({number_of_guests}) exceeds category capacity ({room_category.capacity}).")
        )

    # Server-side availability check
    available_count = check_category_availability(room_category, check_in, check_out)
    if available_count <= 0:
        raise ValidationError(_("No rooms available in this category for the requested dates."))

    reservation = Reservation(
        guest_name=guest_name,
        email=email,
        phone=phone,
        room_category=room_category,
        check_in=check_in,
        check_out=check_out,
        number_of_guests=number_of_guests,
        special_requests=special_requests,
        assigned_room=None,
        status=ReservationStatus.PENDING_REVIEW,
    )
    reservation.save()
    return reservation


@transaction.atomic
def approve_reservation_and_assign_room(
    *,
    reservation_id: int,
    room_id: int,
    staff_user,
    payment_deadline: Optional[datetime] = None,
) -> Reservation:
    """
    Receptionist workflow to approve a reservation and assign a physical room.
    Guarantees:
    - Only authorized staff can perform this operation.
    - Validates assigned room matches category and is operational (active).
    - Uses database transactions and select_for_update() to prevent double bookings.
    - Configurable payment deadline (defaults to DEFAULT_PAYMENT_DEADLINE_HOURS).
    - Status moves to 'awaiting_payment'.
    """
    if not staff_user or not staff_user.is_staff:
        raise PermissionDenied(_("Only authorized hotel staff can approve reservations and assign rooms."))

    # Expire any pending overdue reservations first
    expire_overdue_reservations()

    # Lock reservation and room rows
    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
    room = Room.objects.select_for_update().get(pk=room_id)

    if reservation.status != ReservationStatus.PENDING_REVIEW:
        raise ValidationError(
            _(f"Only reservations in 'pending_review' status can be approved. Current status: '{reservation.status}'.")
        )

    if room.category_id != reservation.room_category_id:
        raise ValidationError(
            _(f"Room {room.room_number} belongs to category '{room.category.name}', "
              f"not '{reservation.room_category.name}'.")
        )

    if room.operational_status != RoomOperationalStatus.ACTIVE:
        raise ValidationError(
            _(f"Room {room.room_number} is currently under maintenance and cannot be assigned.")
        )

    # Check for overlapping blocking reservations on this specific room
    now = timezone.now()
    overlapping = Reservation.objects.select_for_update().filter(
        assigned_room=room,
        check_in__lt=reservation.check_out,
        check_out__gt=reservation.check_in,
    ).filter(
        (models.Q(status=ReservationStatus.CONFIRMED)) |
        (models.Q(status=ReservationStatus.AWAITING_PAYMENT) & (
            models.Q(payment_deadline__isnull=True) | models.Q(payment_deadline__gt=now)
        ))
    ).exclude(pk=reservation.pk)

    if overlapping.exists():
        conflicts = ", ".join(r.reservation_reference for r in overlapping)
        raise ValidationError(
            _(f"Room {room.room_number} has an overlapping booking ({conflicts}) for the selected dates.")
        )

    # Calculate default deadline if not provided
    if not payment_deadline:
        hours = getattr(settings, 'DEFAULT_PAYMENT_DEADLINE_HOURS', 24)
        payment_deadline = timezone.now() + timedelta(hours=hours)

    reservation.assigned_room = room
    reservation.payment_deadline = payment_deadline
    reservation.status = ReservationStatus.AWAITING_PAYMENT
    reservation.save()
    return reservation


@transaction.atomic
def verify_payment_proof(
    *,
    proof_id: int,
    staff_user,
    status: str,
    notes: str = "",
) -> PaymentProof:
    """
    Staff action to review and verify/reject a guest payment proof screenshot.
    Guarantees:
    - Only authorized staff can verify payments.
    - Verification DOES NOT automatically confirm the reservation.
    """
    if not staff_user or not staff_user.is_staff:
        raise PermissionDenied(_("Only authorized hotel staff can verify payments."))

    if status not in PaymentVerificationStatus.values:
        raise ValidationError(_(f"Invalid verification status: '{status}'."))

    proof = PaymentProof.objects.select_for_update().get(pk=proof_id)
    proof.verification_status = status
    proof.verified_by = staff_user
    proof.verification_notes = notes
    proof.save()

    # NOTE: Reservation status is purposefully NOT automatically changed to confirmed!
    return proof


@transaction.atomic
def confirm_reservation(
    *,
    reservation_id: int,
    staff_user,
) -> Reservation:
    """
    Staff action to confirm a reservation after reviewing payment proof.
    Guarantees:
    - Only authorized staff can confirm reservations.
    - Reservation must have an assigned room.
    - Must have at least one verified payment proof.
    - Moves status to 'confirmed'.
    """
    if not staff_user or not staff_user.is_staff:
        raise PermissionDenied(_("Only authorized hotel staff can confirm reservations."))

    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)

    if reservation.status not in [ReservationStatus.AWAITING_PAYMENT, ReservationStatus.PENDING_REVIEW]:
        raise ValidationError(
            _(f"Cannot confirm reservation in status '{reservation.status}'.")
        )

    if not reservation.assigned_room:
        raise ValidationError(_("Cannot confirm reservation without an assigned room."))

    has_verified = reservation.payment_proofs.filter(
        verification_status=PaymentVerificationStatus.VERIFIED
    ).exists()

    if not has_verified:
        raise ValidationError(_("Cannot confirm reservation without at least one verified payment proof."))

    reservation.status = ReservationStatus.CONFIRMED
    reservation.save()
    return reservation


@transaction.atomic
def reject_reservation(
    *,
    reservation_id: int,
    staff_user,
    reason: str = "",
) -> Reservation:
    """
    Staff action to reject a reservation request.
    Releases any assigned physical room.
    """
    if not staff_user or not staff_user.is_staff:
        raise PermissionDenied(_("Only authorized hotel staff can reject reservations."))

    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
    reservation.status = ReservationStatus.REJECTED
    reservation.assigned_room = None
    if reason:
        reservation.special_requests = f"{reservation.special_requests}\n[Staff Rejection Reason: {reason}]".strip()
    reservation.save()
    return reservation
