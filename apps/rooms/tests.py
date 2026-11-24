from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.rooms.models import Room, RoomCategory, RoomImage, RoomOperationalStatus


class RoomModelTests(TestCase):
    def setUp(self):
        self.category = RoomCategory.objects.create(
            name="Deluxe Suite",
            description="Spacious suite with balcony",
            price_per_night=Decimal("150.00"),
            capacity=2,
            is_active=True,
        )

    def test_room_category_creation(self):
        self.assertEqual(self.category.name, "Deluxe Suite")
        self.assertEqual(self.category.capacity, 2)
        self.assertTrue(self.category.is_active)
        self.assertIn("Deluxe Suite", str(self.category))

    def test_physical_room_creation(self):
        room = Room.objects.create(
            room_number="101",
            category=self.category,
            operational_status=RoomOperationalStatus.ACTIVE,
        )
        self.assertEqual(room.room_number, "101")
        self.assertTrue(room.is_operational)
        self.assertIn("101", str(room))

    def test_maintenance_room_not_operational(self):
        room = Room.objects.create(
            room_number="102",
            category=self.category,
            operational_status=RoomOperationalStatus.MAINTENANCE,
        )
        self.assertFalse(room.is_operational)

    def test_unique_room_number(self):
        Room.objects.create(room_number="103", category=self.category)
        with self.assertRaises(Exception):
            Room.objects.create(room_number="103", category=self.category)
