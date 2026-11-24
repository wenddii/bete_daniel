from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import GalleryImage, Facility, HotelInformation


@admin.register(GalleryImage)
class GalleryImageAdmin(admin.ModelAdmin):
    list_display = (
        'thumbnail_preview',
        'title_display',
        'is_hero',
        'is_active',
        'display_order',
        'created_at',
    )
    list_editable = ('is_hero', 'is_active', 'display_order')
    list_filter = ('is_hero', 'is_active', 'created_at')
    search_fields = ('title', 'caption')
    readonly_fields = ('thumbnail_preview_large', 'created_at', 'updated_at')
    actions = ['set_as_hero_action', 'activate_images_action', 'deactivate_images_action']

    fieldsets = (
        (_("Photograph Details"), {
            'fields': (
                'image',
                'thumbnail_preview_large',
                'title',
                'caption',
            )
        }),
        (_("Homepage Display Settings"), {
            'fields': (
                'is_hero',
                'is_active',
                'display_order',
            ),
            'description': _(
                "Check 'Is Hero' to feature this image as the main homepage hero background. "
                "Only one image can be the active hero at a time."
            )
        }),
        (_("Timestamps"), {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description="Preview")
    def thumbnail_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 60px; height: 42px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd;" />',
                obj.image.url
            )
        return _("No file")

    @admin.display(description="Preview (Large)")
    def thumbnail_preview_large(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 320px; max-height: 200px; object-fit: contain; border-radius: 6px; border: 1px solid #ccc;" />',
                obj.image.url
            )
        return _("No image uploaded yet.")

    @admin.display(description="Title")
    def title_display(self, obj):
        return obj.title or format_html('<em>{}</em>', _("Untitled"))

    @admin.display(description="Hero")
    def is_hero_badge(self, obj):
        if obj.is_hero:
            return format_html(
                '<span style="background: #b38e5d; color: #fff; padding: 2px 8px; border-radius: 12px; font-weight: bold; font-size: 0.75rem;">HOMEPAGE HERO</span>'
            )
        return "-"

    @admin.action(description=_("Designate selected image as Homepage Hero"))
    def set_as_hero_action(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                _("Please select exactly one image to set as the homepage hero."),
                messages.WARNING
            )
            return
        selected = queryset.first()
        selected.is_hero = True
        selected.save()
        self.message_user(
            request,
            _(f"Image '{selected}' is now set as the Homepage Hero."),
            messages.SUCCESS
        )

    @admin.action(description=_("Activate selected images"))
    def activate_images_action(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, _(f"{count} image(s) marked as active."), messages.SUCCESS)

    @admin.action(description=_("Deactivate selected images"))
    def deactivate_images_action(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, _(f"{count} image(s) deactivated."), messages.SUCCESS)


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = (
        'thumbnail_preview',
        'name',
        'is_active',
        'display_order',
        'updated_at',
    )
    list_editable = ('is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    readonly_fields = ('thumbnail_preview_large', 'created_at', 'updated_at')

    fieldsets = (
        (_("Service & Amenity Information"), {
            'fields': (
                'name',
                'description',
                'image',
                'thumbnail_preview_large',
            )
        }),
        (_("Display Settings"), {
            'fields': (
                'display_order',
                'is_active',
            )
        }),
        (_("Timestamps"), {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description="Image")
    def thumbnail_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 50px; height: 35px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd;" />',
                obj.image.url
            )
        return _("No image")

    @admin.display(description="Image Preview")
    def thumbnail_preview_large(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 260px; max-height: 160px; object-fit: contain; border-radius: 6px; border: 1px solid #ccc;" />',
                obj.image.url
            )
        return _("No photo uploaded for this service.")


@admin.register(HotelInformation)
class HotelInformationAdmin(admin.ModelAdmin):
    list_display = ('hotel_name', 'phone', 'email', 'updated_at')

    fieldsets = (
        (_("Brand & Tagline"), {
            'fields': (
                'hotel_name',
                'tagline',
            )
        }),
        (_("About Bete Daniel Hotel"), {
            'fields': (
                'about_title',
                'about_description',
            )
        }),
        (_("Location & Contact Details"), {
            'fields': (
                'address',
                'phone',
                'email',
            )
        }),
        (_("Hotel Hours"), {
            'fields': (
                'check_in_time',
                'check_out_time',
                'reception_hours',
            )
        }),
    )

    def has_add_permission(self, request):
        # Prevent creating multiple hotel profiles
        return HotelInformation.objects.count() == 0

    def has_delete_permission(self, request, obj=None):
        return False
