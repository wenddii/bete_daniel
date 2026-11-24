from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class GalleryImage(models.Model):
    """
    Hotel photographs for the homepage hero and gallery showcase.
    Managed exclusively by hotel administrators through Django Admin.
    """
    title = models.CharField(
        max_length=150,
        blank=True,
        help_text=_("Title or label for this photograph")
    )
    caption = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Optional caption displayed alongside the photo")
    )
    image = models.FileField(
        upload_to='gallery/',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])],
        help_text=_("Upload an authentic hotel photograph (JPG, PNG, WebP)")
    )
    is_hero = models.BooleanField(
        default=False,
        help_text=_(
            "Designate this image as the main homepage hero background. "
            "Selecting this will automatically unset any previously chosen hero image."
        )
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text=_("Display order in the gallery (lower numbers appear first)")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Controls whether this image is published on the website")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Hotel Gallery Image")
        verbose_name_plural = _("Hotel Gallery Images")
        ordering = ['display_order', '-created_at']

    def __str__(self):
        label = self.title or f"Photo #{self.id}"
        hero_tag = " [HERO]" if self.is_hero else ""
        return f"{label}{hero_tag}"

    def save(self, *args, **kwargs):
        # If this image is designated as hero, unset is_hero on all other images
        if self.is_hero:
            GalleryImage.objects.filter(is_hero=True).exclude(pk=self.pk).update(is_hero=False)
        super().save(*args, **kwargs)


class Facility(models.Model):
    """
    Services and amenities offered by Bete Daniel Hotel.
    Displayed dynamically on the homepage Services & Amenities section.
    """
    name = models.CharField(
        max_length=120,
        unique=True,
        help_text=_("Name of the service or amenity (e.g. Traditional Coffee Ceremony, Free Wi-Fi)")
    )
    description = models.TextField(
        blank=True,
        help_text=_("Brief description of what this service or amenity provides")
    )
    image = models.FileField(
        upload_to='facilities/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])],
        help_text=_("Optional photo representing this service or amenity")
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text=_("Display order (lower numbers appear first)")
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Controls whether this service is visible on the website")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Service & Amenity")
        verbose_name_plural = _("Services & Amenities")
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class HotelInformation(models.Model):
    """
    Central profile, about text, location and contact details for Bete Daniel Hotel.
    Allows administrators to update information without altering templates.
    """
    hotel_name = models.CharField(
        max_length=150,
        default="Bete Daniel Hotel",
        help_text=_("Official hotel name")
    )
    tagline = models.CharField(
        max_length=255,
        default="A Sanctuary of Warmth, Comfort & Authentic Hospitality",
        blank=True,
        help_text=_("Short header or hero tagline")
    )
    about_title = models.CharField(
        max_length=200,
        default="Welcome to Bete Daniel Hotel",
        blank=True,
        help_text=_("Heading for the About section")
    )
    about_description = models.TextField(
        default=(
            "Nestled in a serene and accessible neighborhood, Bete Daniel Hotel provides a refined "
            "blend of modern comfort and authentic Ethiopian hospitality. Whether you are traveling "
            "for business or leisure, our thoughtfully designed rooms and attentive staff ensure an "
            "unforgettable and restful stay."
        ),
        blank=True,
        help_text=_("Detailed introduction and about narrative")
    )
    address = models.CharField(
        max_length=255,
        default="Bole Sub-City, Addis Ababa, Ethiopia",
        blank=True,
        help_text=_("Physical hotel address")
    )
    phone = models.CharField(
        max_length=50,
        default="+251 11 000 0000",
        blank=True,
        help_text=_("Primary front desk phone number")
    )
    email = models.EmailField(
        default="info@betedanielhotel.com",
        blank=True,
        help_text=_("Public inquiries and reservations email")
    )
    check_in_time = models.CharField(
        max_length=50,
        default="2:00 PM",
        blank=True,
        help_text=_("Standard check-in time")
    )
    check_out_time = models.CharField(
        max_length=50,
        default="11:00 AM",
        blank=True,
        help_text=_("Standard check-out time")
    )
    reception_hours = models.CharField(
        max_length=100,
        default="24/7 Front Desk",
        blank=True,
        help_text=_("Front desk operational hours")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Hotel Information & Profile")
        verbose_name_plural = _("Hotel Information & Profile")

    def __str__(self):
        return self.hotel_name

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj
