from django.db import models
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.utils.translation import gettext_lazy as _


class RoomCategory(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Name of the room category (e.g. Deluxe Suite, Standard Single)")
    )
    description = models.TextField(
        blank=True,
        help_text=_("Detailed description of category features and amenities")
    )
    price_per_night = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text=_("Nightly rate")
    )
    capacity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text=_("Maximum guest capacity")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether this category is active and open for reservations")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Room Category")
        verbose_name_plural = _("Room Categories")
        ordering = ['price_per_night', 'name']

    def __str__(self):
        return f"{self.name} (Cap: {self.capacity}, ${self.price_per_night}/night)"


class RoomOperationalStatus(models.TextChoices):
    ACTIVE = 'active', _('Active')
    MAINTENANCE = 'maintenance', _('Maintenance')


class Room(models.Model):
    room_number = models.CharField(
        max_length=20,
        unique=True,
        help_text=_("Physical room number or identifier (e.g. 101, 204B)")
    )
    category = models.ForeignKey(
        RoomCategory,
        on_delete=models.PROTECT,
        related_name='rooms',
        help_text=_("Category this physical room belongs to")
    )
    operational_status = models.CharField(
        max_length=20,
        choices=RoomOperationalStatus.choices,
        default=RoomOperationalStatus.ACTIVE,
        help_text=_("Current operational status")
    )
    notes = models.TextField(
        blank=True,
        help_text=_("Staff notes regarding physical room status")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Physical Room")
        verbose_name_plural = _("Physical Rooms")
        ordering = ['room_number']

    def __str__(self):
        return f"Room {self.room_number} ({self.category.name}) - {self.get_operational_status_display()}"

    @property
    def is_operational(self):
        return self.operational_status == RoomOperationalStatus.ACTIVE


class RoomImage(models.Model):
    category = models.ForeignKey(
        RoomCategory,
        on_delete=models.CASCADE,
        related_name='images',
        help_text=_("Room category displayed in this image")
    )
    image = models.FileField(
        upload_to='room_categories/',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])],
        help_text=_("Upload an image of this room category (JPG, PNG, WebP)")
    )
    caption = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Optional caption for this image")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Room Category Image")
        verbose_name_plural = _("Room Category Images")
        ordering = ['-created_at']

    def __str__(self):
        return self.caption or f"Image for {self.category.name}"
