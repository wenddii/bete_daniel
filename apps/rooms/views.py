from django.shortcuts import get_object_or_404, render
from apps.core.models import HotelInformation
from .models import RoomCategory


def room_category_list(request):
    """
    Public listing of all available room categories at Bete Daniel Hotel.
    """
    categories = RoomCategory.objects.filter(is_active=True).prefetch_related('images').order_by('price_per_night', 'name')
    hotel_info = HotelInformation.get_solo()
    
    return render(request, 'rooms/category_list.html', {
        'categories': categories,
        'hotel_info': hotel_info,
    })


def room_category_detail(request, category_id: int):
    """
    Detailed presentation of a specific room category, its amenities, capacity, and photo gallery.
    """
    category = get_object_or_404(
        RoomCategory.objects.prefetch_related('images'),
        pk=category_id,
        is_active=True
    )
    hotel_info = HotelInformation.get_solo()

    return render(request, 'rooms/category_detail.html', {
        'category': category,
        'images': category.images.all(),
        'hotel_info': hotel_info,
    })
