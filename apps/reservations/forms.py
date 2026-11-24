from datetime import timedelta
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.rooms.models import Room, RoomCategory, RoomOperationalStatus
from .models import PaymentProof, Reservation
from .services import check_category_availability, get_category_available_rooms


class GuestBookingForm(forms.ModelForm):
    """
    Public booking request form submitted by guests.
    Guests select a room category, NEVER an individual room number.
    All inputs are strictly validated on the server.
    """
    room_category = forms.ModelChoiceField(
        queryset=RoomCategory.objects.filter(is_active=True),
        empty_label=_("— Select a Room Category —"),
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text=_("Select your desired room category")
    )
    check_in = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        help_text=_("Arrival date")
    )
    check_out = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        help_text=_("Departure date")
    )
    number_of_guests = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
        help_text=_("Total guests staying in the room")
    )
    guest_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Abebe Bikila'}),
        help_text=_("Primary guest full name")
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'e.g. name@example.com'}),
        help_text=_("Booking confirmation and updates will be sent here")
    )
    phone = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. +251 91 123 4567'}),
        help_text=_("Contact phone number")
    )
    special_requests = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional: Quiet room, estimated arrival time, dietary notes, etc.'}),
        help_text=_("Any special requests or preferences")
    )

    class Meta:
        model = Reservation
        fields = [
            'room_category',
            'check_in',
            'check_out',
            'number_of_guests',
            'guest_name',
            'email',
            'phone',
            'special_requests',
        ]

    def __init__(self, *args, **kwargs):
        initial_category = kwargs.pop('initial_category', None)
        super().__init__(*args, **kwargs)
        if initial_category:
            self.fields['room_category'].initial = initial_category
        
        # Set HTML5 min date for check-in to today
        today_str = timezone.localdate().isoformat()
        self.fields['check_in'].widget.attrs['min'] = today_str
        self.fields['check_out'].widget.attrs['min'] = today_str

    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in')
        check_out = cleaned_data.get('check_out')
        category = cleaned_data.get('room_category')
        guests = cleaned_data.get('number_of_guests')

        today = timezone.localdate()

        # 1. Date validations
        if check_in and check_in < today:
            self.add_error('check_in', _("Check-in date cannot be in the past."))

        if check_in and check_out:
            if check_out <= check_in:
                self.add_error('check_out', _("Check-out date must be strictly after the check-in date."))

        # 2. Category capacity validation
        if category and guests:
            if not category.is_active:
                self.add_error('room_category', _("This room category is currently not available for booking."))
            elif guests > category.capacity:
                self.add_error(
                    'number_of_guests',
                    _(f"The selected {category.name} accommodates up to {category.capacity} guest(s). "
                      f"You requested {guests}.")
                )

        # 3. Server-side availability validation
        if category and check_in and check_out and check_out > check_in and check_in >= today:
            available_count = check_category_availability(category, check_in, check_out)
            if available_count <= 0:
                self.add_error(
                    'room_category',
                    _(f"No rooms are currently available in the '{category.name}' category for the requested dates. "
                      f"Please select alternative dates or browse another room category.")
                )

        return cleaned_data


class PaymentProofUploadForm(forms.ModelForm):
    """
    Form used by guests to upload payment transfer screenshots or receipts.
    Uploaded files are stored in protected storage.
    """
    screenshot = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.jpg,.jpeg,.png,.webp,.pdf'}),
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'pdf'])],
        help_text=_("Upload a clear screenshot or receipt of your bank transfer (JPG, PNG, WebP, PDF). Maximum 10MB.")
    )

    class Meta:
        model = PaymentProof
        fields = ['screenshot']


class ReceptionistApprovalForm(forms.Form):
    """
    Form used by receptionists in the staff dashboard to approve a reservation,
    assign an operational physical room, and set a payment deadline.
    """
    assigned_room = forms.ModelChoiceField(
        queryset=Room.objects.none(),
        empty_label=_("— Select Physical Room to Assign —"),
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text=_("Only active, non-conflicting rooms in this category are shown.")
    )
    deadline_hours = forms.IntegerField(
        initial=24,
        min_value=1,
        max_value=168,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text=_("Payment deadline in hours from now (e.g. 24 hours)")
    )

    def __init__(self, reservation, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reservation = reservation
        # Populate with available physical rooms for the reservation's dates
        available_rooms = get_category_available_rooms(
            category=reservation.room_category,
            check_in=reservation.check_in,
            check_out=reservation.check_out,
            exclude_reservation_id=reservation.pk
        )
        self.fields['assigned_room'].queryset = available_rooms


class ReceptionistPaymentVerificationForm(forms.Form):
    """
    Form used by receptionists to verify or reject a payment submission with optional notes.
    """
    status = forms.ChoiceField(
        choices=[('verified', _('Verified (Payment Received)')), ('rejected', _('Rejected (Invalid / Unreadable)'))],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    verification_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional internal notes, bank ref, or rejection reason'}),
        help_text=_("Notes regarding this verification decision")
    )
