from django import forms
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.rooms.models import Room, RoomOperationalStatus
from .models import PaymentProof, PaymentVerificationStatus, Reservation, ReservationStatus
from .services import expire_overdue_reservations, reject_reservation


class PaymentProofInline(admin.StackedInline):
    model = PaymentProof
    extra = 0
    can_delete = False
    fields = (
        'screenshot_review',
        'verification_status',
        'verified_by',
        'verification_notes',
        'uploaded_at',
    )
    readonly_fields = ('screenshot_review', 'uploaded_at', 'verified_by')

    @admin.display(description="Protected Screenshot")
    def screenshot_review(self, instance):
        if not instance.pk or not instance.screenshot:
            return _("No document uploaded.")
        url = reverse('reservations:payment_proof_document', kwargs={'proof_id': instance.pk})
        return format_html(
            '<a href="{}" target="_blank" class="button" style="padding: 4px 10px; background: #2563eb; color: #fff; border-radius: 4px; text-decoration: none;">'
            'View Protected Document (Staff Only) &rarr;</a>',
            url
        )


class ReservationAdminForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically restrict assigned_room queryset to active rooms matching the category
        if self.instance and self.instance.pk and self.instance.room_category_id:
            self.fields['assigned_room'].queryset = Room.objects.filter(
                category=self.instance.room_category,
                operational_status=RoomOperationalStatus.ACTIVE
            )
        else:
            self.fields['assigned_room'].queryset = Room.objects.filter(
                operational_status=RoomOperationalStatus.ACTIVE
            )


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    form = ReservationAdminForm
    inlines = [PaymentProofInline]
    date_hierarchy = 'check_in'

    list_display = (
        'reference_display',
        'guest_name',
        'phone',
        'room_category',
        'check_in',
        'check_out',
        'number_of_guests',
        'status_badge',
        'assigned_room',
        'payment_deadline_status',
        'payment_verification_summary',
    )

    list_filter = (
        'status',
        'room_category',
        'check_in',
        'check_out',
        'created_at',
    )

    search_fields = (
        'reservation_reference',
        'guest_name',
        'email',
        'phone',
        'assigned_room__room_number',
    )

    list_select_related = ('room_category', 'assigned_room')

    readonly_fields = (
        'reservation_reference',
        'payment_upload_token',
        'created_at',
        'updated_at',
    )

    fieldsets = (
        (_("Guest Information"), {
            'fields': (
                'guest_name',
                'email',
                'phone',
                'number_of_guests',
                'special_requests',
            )
        }),
        (_("Stay & Category Selection"), {
            'fields': (
                'room_category',
                'check_in',
                'check_out',
            )
        }),
        (_("Receptionist Room Assignment & Lifecycle"), {
            'description': _(
                "Physical rooms can only be assigned by receptionists when approving reservations. "
                "The room must be operational and belong to the selected category."
            ),
            'fields': (
                'status',
                'assigned_room',
                'payment_deadline',
            )
        }),
        (_("Security & Audit Tokens"), {
            'classes': ('collapse',),
            'fields': (
                'reservation_reference',
                'payment_upload_token',
                'created_at',
                'updated_at',
            )
        }),
    )

    actions = ['expire_overdue_action', 'reject_selected_action']

    @admin.display(description="Reference")
    def reference_display(self, obj):
        return format_html("<strong>{}</strong>", obj.reservation_reference)

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            ReservationStatus.PENDING_REVIEW: ('#92400e', '#fef3c7'),      # Amber
            ReservationStatus.AWAITING_PAYMENT: ('#1e40af', '#dbeafe'),    # Blue
            ReservationStatus.CONFIRMED: ('#065f46', '#d1fae5'),           # Emerald
            ReservationStatus.REJECTED: ('#991b1b', '#fee2e2'),            # Red
            ReservationStatus.CANCELLED: ('#374151', '#f3f4f6'),           # Gray
            ReservationStatus.EXPIRED: ('#6b7280', '#e5e7eb'),             # Slate
            ReservationStatus.COMPLETED: ('#312e81', '#e0e7ff'),           # Indigo
        }
        text_color, bg_color = colors.get(obj.status, ('#000', '#eee'))
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 3px 8px; border-radius: 9999px; font-weight: 600; font-size: 0.8rem;">{}</span>',
            bg_color,
            text_color,
            obj.get_status_display()
        )

    @admin.display(description="Payment Deadline")
    def payment_deadline_status(self, obj):
        if not obj.payment_deadline:
            return "-"
        if obj.status == ReservationStatus.AWAITING_PAYMENT and not obj.is_blocking:
            return format_html(
                '<span style="color: #dc2626; font-weight: bold;">Expired ({})</span>',
                obj.payment_deadline.strftime("%Y-%m-%d %H:%M")
            )
        return obj.payment_deadline.strftime("%Y-%m-%d %H:%M")

    @admin.display(description="Payment Proofs")
    def payment_verification_summary(self, obj):
        total = obj.payment_proofs.count()
        if total == 0:
            return _("None")
        verified = obj.payment_proofs.filter(verification_status=PaymentVerificationStatus.VERIFIED).count()
        pending = obj.payment_proofs.filter(verification_status=PaymentVerificationStatus.PENDING).count()
        if verified > 0:
            return format_html('<span style="color: #059669; font-weight: 600;">Verified ({})</span>', verified)
        if pending > 0:
            return format_html('<span style="color: #d97706; font-weight: 600;">Pending ({})</span>', pending)
        return _("Rejected")

    @admin.action(description=_("Expire overdue reservations and release rooms"))
    def expire_overdue_action(self, request, queryset):
        expired_count = expire_overdue_reservations()
        self.message_user(
            request,
            _(f"Successfully processed expirations: {expired_count} overdue reservation(s) expired and released."),
            messages.SUCCESS
        )

    @admin.action(description=_("Reject selected reservations and release rooms"))
    def reject_selected_action(self, request, queryset):
        count = 0
        for res in queryset:
            if res.status not in [ReservationStatus.COMPLETED, ReservationStatus.CANCELLED]:
                reject_reservation(reservation_id=res.pk, staff_user=request.user, reason="Staff rejected via admin")
                count += 1
        self.message_user(
            request,
            _(f"Successfully rejected {count} reservation(s) and released any assigned rooms."),
            messages.SUCCESS
        )


@admin.register(PaymentProof)
class PaymentProofAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'reservation_reference',
        'guest_name',
        'verification_status_badge',
        'view_screenshot_button',
        'uploaded_at',
        'verified_by',
    )
    list_filter = ('verification_status', 'uploaded_at')
    search_fields = (
        'reservation__reservation_reference',
        'reservation__guest_name',
        'verification_notes',
    )
    readonly_fields = ('uploaded_at', 'view_screenshot_button')
    list_select_related = ('reservation', 'verified_by')
    actions = ['verify_payments_action', 'reject_payments_action']

    @admin.display(description="Reservation")
    def reservation_reference(self, obj):
        url = reverse('admin:reservations_reservation_change', args=[obj.reservation_id])
        return format_html('<a href="{}">{}</a>', url, obj.reservation.reservation_reference)

    @admin.display(description="Guest")
    def guest_name(self, obj):
        return obj.reservation.guest_name

    @admin.display(description="Status")
    def verification_status_badge(self, obj):
        colors = {
            PaymentVerificationStatus.PENDING: ('#92400e', '#fef3c7'),
            PaymentVerificationStatus.VERIFIED: ('#065f46', '#d1fae5'),
            PaymentVerificationStatus.REJECTED: ('#991b1b', '#fee2e2'),
        }
        text_color, bg_color = colors.get(obj.verification_status, ('#000', '#eee'))
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 2px 8px; border-radius: 9999px; font-weight: 600;">{}</span>',
            bg_color,
            text_color,
            obj.get_verification_status_display()
        )

    @admin.display(description="Document")
    def view_screenshot_button(self, obj):
        if not obj.screenshot:
            return _("No document")
        url = reverse('reservations:payment_proof_document', kwargs={'proof_id': obj.pk})
        return format_html(
            '<a href="{}" target="_blank" style="font-weight: 600; color: #2563eb;">View Screenshot &rarr;</a>',
            url
        )

    @admin.action(description=_("Verify selected payment proofs"))
    def verify_payments_action(self, request, queryset):
        count = 0
        for proof in queryset:
            proof.verification_status = PaymentVerificationStatus.VERIFIED
            proof.verified_by = request.user
            proof.save(update_fields=['verification_status', 'verified_by'])
            count += 1
        self.message_user(
            request,
            _(f"{count} payment proof(s) marked as verified. (Note: Reservations must still be confirmed manually)."),
            messages.SUCCESS
        )

    @admin.action(description=_("Reject selected payment proofs"))
    def reject_payments_action(self, request, queryset):
        count = 0
        for proof in queryset:
            proof.verification_status = PaymentVerificationStatus.REJECTED
            proof.verified_by = request.user
            proof.save(update_fields=['verification_status', 'verified_by'])
            count += 1
        self.message_user(
            request,
            _(f"{count} payment proof(s) marked as rejected."),
            messages.SUCCESS
        )
