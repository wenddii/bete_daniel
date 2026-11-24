from django.shortcuts import render
from apps.rooms.models import RoomCategory
from .models import Facility, GalleryImage, HotelInformation


def home_view(request):
    """
    Renders the Bete Daniel Hotel homepage.
    All dynamic hotel content (hero, categories, services, gallery, contact)
    is fetched directly from database models managed by the administrator.
    """
    # 1. Main Hero Image (specifically designated by admin)
    hero_image = GalleryImage.objects.filter(is_active=True, is_hero=True).first()

    # 2. Room Categories (with active status and associated photos)
    room_categories = RoomCategory.objects.filter(
        is_active=True
    ).prefetch_related('images').order_by('price_per_night', 'name')

    # 3. Services & Amenities
    facilities = Facility.objects.filter(is_active=True).order_by('display_order', 'name')

    # 4. Hotel Gallery Images
    gallery_images = GalleryImage.objects.filter(is_active=True).order_by('display_order', '-created_at')

    # 5. Hotel Profile & Contact Info
    hotel_info = HotelInformation.get_solo()

    context = {
        'hero_image': hero_image,
        'room_categories': room_categories,
        'facilities': facilities,
        'gallery_images': gallery_images,
        'hotel_info': hotel_info,
    }
    return render(request, 'core/home.html', context)
