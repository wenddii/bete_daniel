import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.rooms.models import Room, RoomCategory, RoomOperationalStatus


class ProtectedPaymentStorage(FileSystemStorage):
    """
    Dedicated storage for sensitive payment verification screenshots.
    Files are stored outside public media without an automatic public URL.
    """
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', settings.PROTECTED_MEDIA_ROOT)
        kwargs.setdefault('base_url', None)
        super().__init__(*args, **kwargs)


protected_payment_storage = ProtectedPaymentStorage()


def generate_reservation_reference():
    """Generates an unguessable booking reference code."""
    return f"BDH-{secrets.token_hex(4).upper()}"


def generate_payment_upload_token():
    """Generates a cryptographically secure, unguessable payment upload token."""
    return secrets.token_urlsafe(32)


class ReservationStatus(models.TextChoices):
    PENDING_REVIEW = 'pending_review', _('Pending Review')
    AWAITING_PAYMENT = 'awaiting_payment', _('Awaiting Payment')
    CONFIRMED = 'confirmed', _('Confirmed')
    REJECTED = 'rejected', _('Rejected')
    CANCELLED = 'cancelled', _('Cancelled')
    EXPIRED = 'expired', _('Expired')
    COMPLETED = 'completed', _('Completed')


class Reservation(models.Model):
    guest_name = models.CharField(
        max_length=150,
        help_text=_("Full name of the primary guest")
    )
    email = models.EmailField(
        help_text=_("Guest email address for booking notifications")
    )
    phone = models.CharField(
        max_length=30,
        help_text=_("Guest contact phone number")
    )
    room_category = models.ForeignKey(
        RoomCategory,
        on_delete=models.PROTECT,
        related_name='reservations',
        help_text=_("Room category requested by the guest")
    )
    check_in = models.DateField(
        help_text=_("Scheduled check-in date")
    )
    check_out = models.DateField(
        help_text=_("Scheduled check-out date")
    )
    number_of_guests = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text=_("Total number of guests staying in the room")
    )
    special_requests = models.TextField(
        blank=True,
        help_text=_("Optional guest requests (e.g. quiet room, late check-in)")
    )
    assigned_room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reservations',
        help_text=_("Specific physical room assigned by the receptionist")
    )
    reservation_reference = models.CharField(
        max_length=32,
        unique=True,
        default=generate_reservation_reference,
        editable=False,
        help_text=_("Unique public booking reference (e.g. BDH-A1B2C3D4)")
    )
    payment_upload_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_payment_upload_token,
        editable=False,
        help_text=_("Secure unguessable token for uploading payment proof")
    )
    payment_deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Deadline for guest to upload payment before reservation expires")
    )
    status = models.CharField(
        max_length=25,
        choices=ReservationStatus.choices,
        default=ReservationStatus.PENDING_REVIEW,
        help_text=_("Current lifecycle status of this reservation")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Reservation")
        verbose_name_plural = _("Reservations")
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reservation_reference} - {self.guest_name} ({self.get_status_display()})"

    @property
    def is_blocking(self):
        """
        Determines if this reservation holds/blocks a physical room.
        A reservation blocks if it is confirmed or awaiting payment with an active deadline.
        """
        if self.status == ReservationStatus.CONFIRMED:
            return True
        if self.status == ReservationStatus.AWAITING_PAYMENT:
            if self.payment_deadline is None:
                return True
            return self.payment_deadline > timezone.now()
        return False

    @property
    def total_nights(self):
        if self.check_in and self.check_out and self.check_out > self.check_in:
            return (self.check_out - self.check_in).days
        return 0

    @property
    def total_price(self):
        if self.room_category and self.total_nights:
            return self.room_category.price_per_night * self.total_nights
        return 0

    @property
    def is_payment_overdue(self):
        if self.status == ReservationStatus.AWAITING_PAYMENT and self.payment_deadline:
            return self.payment_deadline <= timezone.now()
        return False

    def clean(self):
        super().clean()
        errors = {}

        # 1. Date validations
        if self.check_in and self.check_out:
            if self.check_out <= self.check_in:
                errors['check_out'] = _("Check-out date must be strictly after the check-in date.")

            # For new reservations, prevent past check-in dates
            if not self.pk and self.check_in < timezone.localdate():
                errors['check_in'] = _("Check-in date cannot be in the past.")

        # 2. Capacity validation
        if self.room_category and self.number_of_guests:
            if self.number_of_guests > self.room_category.capacity:
                errors['number_of_guests'] = _(
                    f"Number of guests ({self.number_of_guests}) exceeds category capacity ({self.room_category.capacity})."
                )

        # 3. Assigned room validations
        if self.assigned_room:
            # Physical room category match
            if self.assigned_room.category_id != self.room_category_id:
                errors['assigned_room'] = _(
                    f"Assigned room {self.assigned_room.room_number} belongs to category "
                    f"'{self.assigned_room.category.name}', not '{self.room_category.name}'."
                )

            # Room operational status
            if self.assigned_room.operational_status != RoomOperationalStatus.ACTIVE:
                errors['assigned_room'] = _(
                    f"Room {self.assigned_room.room_number} is currently under maintenance and cannot be assigned."
                )

            # Overlapping assignments check for active blocking reservations
            if self.check_in and self.check_out:
                overlapping = Reservation.objects.filter(
                    assigned_room=self.assigned_room,
                    status__in=[ReservationStatus.AWAITING_PAYMENT, ReservationStatus.CONFIRMED],
                    check_in__lt=self.check_out,
                    check_out__gt=self.check_in,
                )
                if self.pk:
                    overlapping = overlapping.exclude(pk=self.pk)

                # Filter out expired awaiting_payment
                now = timezone.now()
                blocking_overlap = [
                    res for res in overlapping
                    if res.status == ReservationStatus.CONFIRMED or (
                        res.status == ReservationStatus.AWAITING_PAYMENT and (res.payment_deadline is None or res.payment_deadline > now)
                    )
                ]
                if blocking_overlap:
                    conflict_refs = ", ".join(r.reservation_reference for r in blocking_overlap)
                    errors['assigned_room'] = _(
                        f"Room {self.assigned_room.room_number} has an overlapping booking with: {conflict_refs}."
                    )

        # 4. Status transition requirements
        if self.status in [ReservationStatus.AWAITING_PAYMENT, ReservationStatus.CONFIRMED] and not self.assigned_room:
            errors['assigned_room'] = _(
                f"A physical room must be assigned to set status to '{self.get_status_display()}'."
            )

        if self.status == ReservationStatus.AWAITING_PAYMENT and not self.payment_deadline:
            errors['payment_deadline'] = _(
                "A payment deadline is required when a reservation is awaiting payment."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.reservation_reference:
            self.reservation_reference = generate_reservation_reference()
        if not self.payment_upload_token:
            self.payment_upload_token = generate_payment_upload_token()
        self.full_clean()
        super().save(*args, **kwargs)


class PaymentVerificationStatus(models.TextChoices):
    PENDING = 'pending', _('Pending')
    VERIFIED = 'verified', _('Verified')
    REJECTED = 'rejected', _('Rejected')


class PaymentProof(models.Model):
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name='payment_proofs',
        help_text=_("Reservation this payment proof belongs to")
    )
    screenshot = models.FileField(
        storage=protected_payment_storage,
        upload_to='payment_proofs/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'pdf'])],
        help_text=_("Protected payment receipt or bank transfer screenshot")
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Timestamp when proof was uploaded")
    )
    verification_status = models.CharField(
        max_length=20,
        choices=PaymentVerificationStatus.choices,
        default=PaymentVerificationStatus.PENDING,
        help_text=_("Staff verification outcome")
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_payments',
        help_text=_("Staff member who verified or rejected this payment proof")
    )
    verification_notes = models.TextField(
        blank=True,
        help_text=_("Staff notes or comments regarding payment verification")
    )

    class Meta:
        verbose_name = _("Payment Proof")
        verbose_name_plural = _("Payment Proofs")
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"PaymentProof #{self.id} for {self.reservation.reservation_reference} ({self.get_verification_status_display()})"

    @property
    def is_verified(self):
        return self.verification_status == PaymentVerificationStatus.VERIFIED
