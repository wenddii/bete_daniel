from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import Facility, GalleryImage, HotelInformation
from apps.rooms.models import RoomCategory


class CoreModelTests(TestCase):
    def test_gallery_image_creation_and_hero_singleton_behavior(self):
        img1_file = SimpleUploadedFile("hero1.jpg", b"fake_bytes_1", content_type="image/jpeg")
        img2_file = SimpleUploadedFile("hero2.jpg", b"fake_bytes_2", content_type="image/jpeg")

        photo1 = GalleryImage.objects.create(
            title="Lobby View",
            caption="Spacious and serene lobby",
            image=img1_file,
            is_hero=True,
            is_active=True,
        )
        self.assertTrue(photo1.is_hero)
        self.assertIn("[HERO]", str(photo1))

        # Designating photo2 as hero should automatically unset photo1 as hero
        photo2 = GalleryImage.objects.create(
            title="Exterior Night View",
            caption="Hotel exterior illuminated at night",
            image=img2_file,
            is_hero=True,
            is_active=True,
        )
        photo1.refresh_from_db()
        self.assertFalse(photo1.is_hero)
        self.assertTrue(photo2.is_hero)

    def test_facility_creation_and_ordering(self):
        f2 = Facility.objects.create(name="Free High-Speed Wi-Fi", display_order=2)
        f1 = Facility.objects.create(name="Traditional Ethiopian Coffee Ceremony", display_order=1)

        facilities = list(Facility.objects.filter(is_active=True))
        self.assertEqual(facilities, [f1, f2])

    def test_hotel_information_singleton(self):
        info1 = HotelInformation.get_solo()
        self.assertEqual(info1.hotel_name, "Bete Daniel Hotel")

        info1.phone = "+251 11 999 8888"
        info1.save()

        info2 = HotelInformation.get_solo()
        self.assertEqual(info2.phone, "+251 11 999 8888")
        self.assertEqual(HotelInformation.objects.count(), 1)


class HomePageViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.home_url = reverse('core:home')

    def test_homepage_loads_cleanly_when_database_is_empty(self):
        """
        Verifies that an empty database (no images, no services, no room categories)
        renders cleanly without 500 errors, broken tags, or generic stock images.
        """
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/home.html')
        self.assertTemplateUsed(response, 'base.html')

        # Check clean neutral fallback sections
        self.assertContains(response, "hero-neutral-fallback")
        self.assertContains(response, "Accommodations in Preparation")
        self.assertContains(response, "Services & Amenities")
        self.assertContains(response, "Gallery Being Curated")

    def test_homepage_displays_dynamic_content_when_populated(self):
        """
        Verifies that uploaded hero images, room categories, facilities, and gallery images
        are dynamically rendered with their actual media URLs and metadata.
        """
        # 1. Create a Hero Image
        hero_file = SimpleUploadedFile("lobby_hero.jpg", b"hero_img_data", content_type="image/jpeg")
        hero = GalleryImage.objects.create(
            title="Grand Entrance",
            caption="Welcoming lobby area",
            image=hero_file,
            is_hero=True,
            is_active=True,
        )

        # 2. Create another Gallery Image (not hero)
        gallery_file = SimpleUploadedFile("restaurant.jpg", b"restaurant_img_data", content_type="image/jpeg")
        gallery_img = GalleryImage.objects.create(
            title="Dining Hall",
            caption="Authentic local dishes",
            image=gallery_file,
            is_hero=False,
            is_active=True,
        )

        # 3. Create an Inactive Gallery Image (must NOT be rendered)
        hidden_file = SimpleUploadedFile("hidden.jpg", b"hidden_img_data", content_type="image/jpeg")
        GalleryImage.objects.create(
            title="Private Staff Room",
            image=hidden_file,
            is_hero=False,
            is_active=False,
        )

        # 4. Create Room Category
        category = RoomCategory.objects.create(
            name="Executive Suite",
            description="Premium king suite with city view",
            price_per_night=Decimal("250.00"),
            capacity=2,
            is_active=True,
        )

        # 5. Create Facility / Service
        facility_file = SimpleUploadedFile("coffee.jpg", b"coffee_img_data", content_type="image/jpeg")
        facility = Facility.objects.create(
            name="Traditional Coffee Ceremony",
            description="Daily freshly roasted Ethiopian coffee experience.",
            image=facility_file,
            display_order=1,
            is_active=True,
        )

        # Render homepage
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 200)

        # Hero image check
        self.assertContains(response, "hero-with-image")
        self.assertContains(response, hero.image.url)

        # Gallery image check
        self.assertContains(response, gallery_img.image.url)
        self.assertContains(response, "Dining Hall")
        self.assertNotContains(response, "Private Staff Room")

        # Room category check
        self.assertContains(response, "Executive Suite")
        self.assertContains(response, "250.00")
        self.assertContains(response, "Up to 2 Guests")

        # Facility check
        self.assertContains(response, "Traditional Coffee Ceremony")
        self.assertContains(response, facility.image.url)
