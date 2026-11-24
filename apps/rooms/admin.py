from django.contrib import admin
from .models import RoomCategory, Room, RoomImage


class RoomImageInline(admin.TabularInline):
    model = RoomImage
    extra = 1
    fields = ('image', 'caption')


class RoomInline(admin.TabularInline):
    model = Room
    extra = 0
    fields = ('room_number', 'operational_status', 'notes')
    show_change_link = True


@admin.register(RoomCategory)
class RoomCategoryAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'price_per_night',
        'capacity',
        'is_active',
        'total_rooms_count',
        'active_rooms_count',
        'updated_at',
    )
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    inlines = [RoomInline, RoomImageInline]

    @admin.display(description="Total Rooms")
    def total_rooms_count(self, obj):
        return obj.rooms.count()

    @admin.display(description="Active Rooms")
    def active_rooms_count(self, obj):
        return obj.rooms.filter(operational_status='active').count()


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = (
        'room_number',
        'category',
        'operational_status',
        'updated_at',
    )
    list_filter = ('operational_status', 'category')
    search_fields = ('room_number', 'category__name', 'notes')
    list_select_related = ('category',)


@admin.register(RoomImage)
class RoomImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'category', 'caption', 'created_at')
    list_filter = ('category',)
    search_fields = ('caption', 'category__name')
