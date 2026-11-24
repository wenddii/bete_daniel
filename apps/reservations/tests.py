from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.reservations.models import (
    PaymentProof,
    PaymentVerificationStatus,
    Reservation,
    ReservationStatus,
)
from apps.reservations.services import (
    approve_reservation_and_assign_room,
    check_category_availability,
    confirm_reservation,
    create_guest_reservation,
    expire_overdue_reservations,
    get_category_available_rooms,
    reject_reservation,
    verify_payment_proof,
)
from apps.rooms.models import Room, RoomCategory, RoomOperationalStatus

User = get_user_model()


class ReservationWorkflowTests(TestCase):
    def setUp(self):
        # Create categories
        self.deluxe = RoomCategory.objects.create(
            name="Deluxe King",
            description="Luxury room with king bed",
            price_per_night=Decimal("200.00"),
            capacity=2,
            is_active=True,
        )
        self.standard = RoomCategory.objects.create(
            name="Standard Double",
            description="Standard room with twin beds",
            price_per_night=Decimal("100.00"),
            capacity=2,
            is_active=True,
        )

        # Create physical rooms for Deluxe (2 rooms)
        self.room_101 = Room.objects.create(
            room_number="101",
            category=self.deluxe,
            operational_status=RoomOperationalStatus.ACTIVE,
        )
        self.room_102 = Room.objects.create(
            room_number="102",
            category=self.deluxe,
            operational_status=RoomOperationalStatus.ACTIVE,
        )
        # Create physical room in maintenance
        self.room_103_maint = Room.objects.create(
            room_number="103",
            category=self.deluxe,
            operational_status=RoomOperationalStatus.MAINTENANCE,
        )

        # Create physical room for Standard
        self.room_201 = Room.objects.create(
            room_number="201",
            category=self.standard,
            operational_status=RoomOperationalStatus.ACTIVE,
        )

        # Create staff user and regular customer user
        self.staff_user = User.objects.create_user(
            username="receptionist",
            password="securestaffpassword123",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="regular_guest",
            password="regularpassword123",
            is_staff=False,
        )

        # Target dates in future
        self.base_date = timezone.localdate() + timedelta(days=10)
        self.check_in = self.base_date
        self.check_out = self.base_date + timedelta(days=3)

    # -------------------------------------------------------------
    # 1. Room Availability Tests
    # -------------------------------------------------------------
    def test_initial_availability_counts_only_active_physical_rooms(self):
        # Deluxe has 3 rooms: 2 active, 1 maintenance.
        # Availability should be exactly 2.
        available = check_category_availability(self.deluxe, self.check_in, self.check_out)
        self.assertEqual(available, 2)

        available_rooms = get_category_available_rooms(self.deluxe, self.check_in, self.check_out)
        self.assertIn(self.room_101, available_rooms)
        self.assertIn(self.room_102, available_rooms)
        self.assertNotIn(self.room_103_maint, available_rooms)

    def test_guest_creates_reservation_by_category_without_room_assignment(self):
        res = create_guest_reservation(
            guest_name="Abebe Bikila",
            email="abebe@example.com",
            phone="+251911223344",
            room_category=self.deluxe,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=2,
            special_requests="High floor",
        )
        self.assertEqual(res.status, ReservationStatus.PENDING_REVIEW)
        self.assertIsNone(res.assigned_room)
        self.assertTrue(res.reservation_reference.startswith("BDH-"))
        self.assertTrue(len(res.payment_upload_token) >= 32)

        # Pending reservations MUST NOT consume room availability!
        available = check_category_availability(self.deluxe, self.check_in, self.check_out)
        self.assertEqual(available, 2)

    def test_capacity_validation_rejects_excess_guests(self):
        with self.assertRaises(ValidationError):
            create_guest_reservation(
                guest_name="Too Many Guests",
                email="guest@example.com",
                phone="+251900000000",
                room_category=self.deluxe,
                check_in=self.check_in,
                check_out=self.check_out,
                number_of_guests=5,  # Deluxe capacity is 2
            )

    def test_date_validation_rejects_checkout_before_checkin(self):
        with self.assertRaises(ValidationError):
            create_guest_reservation(
                guest_name="Invalid Dates",
                email="guest@example.com",
                phone="+251900000000",
                room_category=self.deluxe,
                check_in=self.check_out,
                check_out=self.check_in,  # Check out before check in
                number_of_guests=1,
            )

    # -------------------------------------------------------------
    # 2. Receptionist Approval & Room Assignment Tests
    # -------------------------------------------------------------
    def test_only_staff_can_approve_reservation_and_assign_room(self):
        res = create_guest_reservation(
            guest_name="Sara Connor",
            email="sara@example.com",
            phone="+251912345678",
            room_category=self.deluxe,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=1,
        )

        # Non-staff attempt must fail
        with self.assertRaises(PermissionDenied):
            approve_reservation_and_assign_room(
                reservation_id=res.pk,
                room_id=self.room_101.pk,
                staff_user=self.regular_user,
            )

        # Staff approval succeeds
        approved_res = approve_reservation_and_assign_room(
            reservation_id=res.pk,
            room_id=self.room_101.pk,
            staff_user=self.staff_user,
        )
        self.assertEqual(approved_res.status, ReservationStatus.AWAITING_PAYMENT)
        self.assertEqual(approved_res.assigned_room, self.room_101)
        self.assertIsNotNone(approved_res.payment_deadline)

        # Now room_101 is awaiting payment, so available rooms for Deluxe drops to 1
        available = check_category_availability(self.deluxe, self.check_in, self.check_out)
        self.assertEqual(available, 1)

    def test_cannot_assign_room_from_different_category(self):
        res = create_guest_reservation(
            guest_name="Guest X",
            email="x@example.com",
            phone="+251911111111",
            room_category=self.deluxe,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=2,
        )
        # room_201 is Standard Double, reservation is Deluxe King
        with self.assertRaises(ValidationError):
            approve_reservation_and_assign_room(
                reservation_id=res.pk,
                room_id=self.room_201.pk,
                staff_user=self.staff_user,
            )

    def test_cannot_assign_room_under_maintenance(self):
        res = create_guest_reservation(
            guest_name="Guest Y",
            email="y@example.com",
            phone="+251922222222",
            room_category=self.deluxe,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=2,
        )
        with self.assertRaises(ValidationError):
            approve_reservation_and_assign_room(
                reservation_id=res.pk,
                room_id=self.room_103_maint.pk,
                staff_user=self.staff_user,
            )

    # -------------------------------------------------------------
    # 3. Overlapping Reservation & Double Booking Tests
    # -------------------------------------------------------------
    def test_reject_overlapping_room_assignments(self):
        # Guest 1: Days 10 to 13, assigned room 101
        res1 = create_guest_reservation(
            guest_name="Guest 1",
            email="g1@example.com",
            phone="+251911000001",
            room_category=self.deluxe,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=1,
        )
        approve_reservation_and_assign_room(
            reservation_id=res1.pk,
            room_id=self.room_101.pk,
            staff_user=self.staff_user,
        )

        # Guest 2: Days 11 to 14 (overlaps with Guest 1!)
        res2 = create_guest_reservation(
            guest_name="Guest 2",
            email="g2@example.com",
            phone="+251911000002",
            room_category=self.deluxe,
            check_in=self.check_in + timedelta(days=1),
            check_out=self.check_out + timedelta(days=1),
            number_of_guests=1,
        )

        # Attempting to assign room 101 to Guest 2 must be rejected!
        with self.assertRaises(ValidationError):
            approve_reservation_and_assign_room(
                reservation_id=res2.pk,
                room_id=self.room_101.pk,
                staff_user=self.staff_user,
            )

        # But assigning room 102 (which is free) should succeed!
        approve_reservation_and_assign_room(
            reservation_id=res2.pk,
            room_id=self.room_102.pk,
            staff_user=self.staff_user,
        )
        res2.refresh_from_db()
        self.assertEqual(res2.assigned_room, self.room_102)

    def test_non_overlapping_consecutive_reservations_are_allowed(self):
        # Guest 1 checks in on base_date, checks out on base_date + 3
        res1 = create_guest_reservation(
            guest_name="Guest Morning Checkout",
            email="mc@example.com",
            phone="+251911000003",
            room_category=self.deluxe,
            check_in=self.base_date,
            check_out=self.base_date + timedelta(days=3),
            number_of_guests=1,
        )
        approve_reservation_and_assign_room(
            reservation_id=res1.pk,
            room_id=self.room_101.pk,
            staff_user=self.staff_user,
        )

        # Guest 2 checks in on base_date + 3 (same day Guest 1 checks out!)
        res2 = create_guest_reservation(
            guest_name="Guest Afternoon Checkin",
            email="ac@example.com",
            phone="+251911000004",
            room_category=self.deluxe,
            check_in=self.base_date + timedelta(days=3),
            check_out=self.base_date + timedelta(days=6),
            number_of_guests=1,
        )

        # Same room 101 can be assigned because dates do not overlap!
        approve_reservation_and_assign_room(
            reservation_id=res2.pk,
            room_id=self.room_101.pk,
            staff_user=self.staff_user,
        )
        res2.refresh_from_db()
        self.assertEqual(res2.assigned_room, self.room_101)

    # -------------------------------------------------------------
    # 4. Payment Proof & Verification Tests
    # -------------------------------------------------------------
    def test_payment_proof_upload_does_not_auto_confirm_reservation(self):
        res = create_guest_reservation(
            guest_name="Payment Tester",
            email="pay@example.com",
            phone="+251911888999",
            room_category=self.deluxe,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=1,
        )
        approve_reservation_and_assign_room(
            reservation_id=res.pk,
            room_id=self.room_101.pk,
            staff_user=self.staff_user,
        )

        # Guest uploads screenshot
        dummy_file = SimpleUploadedFile("receipt.png", b"fake_png_data", content_type="image/png")
        proof = PaymentProof.objects.create(
            reservation=res,
            screenshot=dummy_file,
            verification_status=PaymentVerificationStatus.PENDING,
        )

        res.refresh_from_db()
        # MUST remain awaiting_payment, NEVER automatically confirmed!
        self.assertEqual(res.status, ReservationStatus.AWAITING_PAYMENT)
        self.assertEqual(proof.verification_status, PaymentVerificationStatus.PENDING)

    def test_staff_payment_verification_and_manual_confirmation(self):
        res = create_guest_reservation(
            guest_name="Verified Guest",
            email="vg@example.com",
            phone="+251911777888",
            room_category=self.deluxe,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=2,
        )
        approve_reservation_and_assign_room(
            reservation_id=res.pk,
            room_id=self.room_101.pk,
            staff_user=self.staff_user,
        )

        dummy_file = SimpleUploadedFile("transfer.jpg", b"fake_transfer_bytes", content_type="image/jpeg")
        proof = PaymentProof.objects.create(
            reservation=res,
            screenshot=dummy_file,
        )

        # Non-staff cannot verify
        with self.assertRaises(PermissionDenied):
            verify_payment_proof(
                proof_id=proof.pk,
                staff_user=self.regular_user,
                status=PaymentVerificationStatus.VERIFIED,
            )

        # Non-staff cannot confirm
        with self.assertRaises(PermissionDenied):
            confirm_reservation(
                reservation_id=res.pk,
                staff_user=self.regular_user,
            )

        # Cannot confirm reservation before payment proof is verified
        with self.assertRaises(ValidationError):
            confirm_reservation(
                reservation_id=res.pk,
                staff_user=self.staff_user,
            )

        # Staff verifies payment proof
        verified_proof = verify_payment_proof(
            proof_id=proof.pk,
            staff_user=self.staff_user,
            status=PaymentVerificationStatus.VERIFIED,
            notes="Bank transfer transaction ref verified against hotel bank statement.",
        )
        self.assertEqual(verified_proof.verification_status, PaymentVerificationStatus.VERIFIED)
        self.assertEqual(verified_proof.verified_by, self.staff_user)

        # Now staff confirms reservation
        confirmed_res = confirm_reservation(
            reservation_id=res.pk,
            staff_user=self.staff_user,
        )
        self.assertEqual(confirmed_res.status, ReservationStatus.CONFIRMED)

    # -------------------------------------------------------------
    # 5. Overdue Payment Deadline & Room Release Tests
    # -------------------------------------------------------------
    def test_expired_reservation_releases_assigned_room(self):
        res = create_guest_reservation(
            guest_name="Slow Payer",
            email="slow@example.com",
            phone="+251911555666",
            room_category=self.deluxe,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=1,
        )
        # Set a past deadline (e.g. 1 hour ago)
        past_deadline = timezone.now() - timedelta(hours=1)
        approve_reservation_and_assign_room(
            reservation_id=res.pk,
            room_id=self.room_101.pk,
            staff_user=self.staff_user,
            payment_deadline=past_deadline,
        )

        # Expire overdue reservations
        expired_count = expire_overdue_reservations()
        self.assertGreaterEqual(expired_count, 1)

        res.refresh_from_db()
        self.assertEqual(res.status, ReservationStatus.EXPIRED)
        self.assertIsNone(res.assigned_room)

        # Room 101 should be completely free again!
        available = check_category_availability(self.deluxe, self.check_in, self.check_out)
        self.assertEqual(available, 2)

    # -------------------------------------------------------------
    # 6. Security: Protected Payment Screenshot Access
    # -------------------------------------------------------------
    def test_payment_proof_screenshot_is_protected_from_public_access(self):
        res = create_guest_reservation(
            guest_name="Private Payer",
            email="private@example.com",
            phone="+251911333444",
            room_category=self.deluxe,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=1,
        )
        dummy_file = SimpleUploadedFile("sensitive_statement.png", b"private_data", content_type="image/png")
        proof = PaymentProof.objects.create(
            reservation=res,
            screenshot=dummy_file,
        )

        url = reverse('reservations:payment_proof_document', kwargs={'proof_id': proof.pk})
        client = Client()

        # Anonymous user must be redirected to login
        response = client.get(url)
        self.assertEqual(response.status_code, 302)

        # Regular non-staff user must be rejected
        client.force_login(self.regular_user)
        response_non_staff = client.get(url)
        # staff_member_required redirects non-staff to login or raises 403
        self.assertIn(response_non_staff.status_code, [302, 403])

        # Staff member can access the file
        client.force_login(self.staff_user)
        response_staff = client.get(url)
        self.assertEqual(response_staff.status_code, 200)
        self.assertEqual(b"".join(response_staff.streaming_content), b"private_data")



class EndToEndBookingWorkflowTests(TestCase):
    def setUp(self):
        self.deluxe = RoomCategory.objects.create(
            name="Deluxe King Suite",
            description="High-floor suite with balcony and city view",
            price_per_night=Decimal("180.00"),
            capacity=2,
            is_active=True,
        )
        self.room_101 = Room.objects.create(
            room_number="101",
            category=self.deluxe,
            operational_status=RoomOperationalStatus.ACTIVE,
        )
        self.room_102 = Room.objects.create(
            room_number="102",
            category=self.deluxe,
            operational_status=RoomOperationalStatus.ACTIVE,
        )
        self.room_103_maint = Room.objects.create(
            room_number="103",
            category=self.deluxe,
            operational_status=RoomOperationalStatus.MAINTENANCE,
        )

        self.staff_user = User.objects.create_user(
            username="receptionist_jane",
            password="pass1234password",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="regular_guest_tom",
            password="pass1234password",
            is_staff=False,
        )

        self.client = Client()
        self.check_in = timezone.localdate() + timedelta(days=5)
        self.check_out = timezone.localdate() + timedelta(days=8)

    def test_room_category_list_and_detail_views(self):
        # 1. Listing page
        res = self.client.get(reverse('rooms:category_list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Deluxe King Suite")
        self.assertContains(res, "180.00")

        # 2. Detail page
        res_detail = self.client.get(reverse('rooms:category_detail', kwargs={'category_id': self.deluxe.pk}))
        self.assertEqual(res_detail.status_code, 200)
        self.assertContains(res_detail, "Deluxe King Suite")
        self.assertContains(res_detail, "High-floor suite")

    def test_guest_booking_form_submission_success(self):
        # GET booking form with pre-selected category
        get_res = self.client.get(reverse('reservations:book_category', kwargs={'category_id': self.deluxe.pk}))
        self.assertEqual(get_res.status_code, 200)

        # POST booking request
        payload = {
            'room_category': self.deluxe.pk,
            'check_in': self.check_in.isoformat(),
            'check_out': self.check_out.isoformat(),
            'number_of_guests': 2,
            'guest_name': "Solomon Tekle",
            'email': "solomon@example.com",
            'phone': "+251911001122",
            'special_requests': "Quiet room away from elevator",
        }
        post_res = self.client.post(reverse('reservations:book'), data=payload)
        self.assertEqual(post_res.status_code, 302)

        reservation = Reservation.objects.get(email="solomon@example.com")
        self.assertEqual(reservation.status, ReservationStatus.PENDING_REVIEW)
        self.assertIsNone(reservation.assigned_room)
        self.assertEqual(reservation.total_nights, 3)
        self.assertEqual(reservation.total_price, Decimal("540.00"))

        # Verify redirect to success page
        success_url = reverse('reservations:booking_success', kwargs={'reference': reservation.reservation_reference})
        self.assertRedirects(post_res, success_url)

        # Success page loads cleanly
        success_res = self.client.get(success_url)
        self.assertEqual(success_res.status_code, 200)
        self.assertContains(success_res, reservation.reservation_reference)
        self.assertContains(success_res, "Solomon Tekle")

    def test_booking_form_validation_errors(self):
        # 1. Past check-in date
        past_payload = {
            'room_category': self.deluxe.pk,
            'check_in': (timezone.localdate() - timedelta(days=2)).isoformat(),
            'check_out': (timezone.localdate() + timedelta(days=1)).isoformat(),
            'number_of_guests': 1,
            'guest_name': "Past Booker",
            'email': "past@example.com",
            'phone': "+251911000000",
        }
        res = self.client.post(reverse('reservations:book'), data=past_payload)
        self.assertEqual(res.status_code, 200)
        self.assertFormError(res.context['form'], 'check_in', "Check-in date cannot be in the past.")

        # 2. Check-out before check-in
        inverted_dates_payload = {
            'room_category': self.deluxe.pk,
            'check_in': self.check_out.isoformat(),
            'check_out': self.check_in.isoformat(),
            'number_of_guests': 1,
            'guest_name': "Inverted Booker",
            'email': "inverted@example.com",
            'phone': "+251911000000",
        }
        res = self.client.post(reverse('reservations:book'), data=inverted_dates_payload)
        self.assertEqual(res.status_code, 200)
        self.assertFormError(res.context['form'], 'check_out', "Check-out date must be strictly after the check-in date.")

        # 3. Capacity exceeded (Deluxe capacity is 2)
        excess_guests_payload = {
            'room_category': self.deluxe.pk,
            'check_in': self.check_in.isoformat(),
            'check_out': self.check_out.isoformat(),
            'number_of_guests': 4,
            'guest_name': "Large Family",
            'email': "family@example.com",
            'phone': "+251911000000",
        }
        res = self.client.post(reverse('reservations:book'), data=excess_guests_payload)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context['form'].has_error('number_of_guests'))

    def test_receptionist_dashboard_requires_staff(self):
        # Anonymous visitor redirected to login
        res_anon = self.client.get(reverse('reservations:reception_dashboard'))
        self.assertEqual(res_anon.status_code, 302)

        # Regular non-staff user redirected or 403
        self.client.force_login(self.regular_user)
        res_guest = self.client.get(reverse('reservations:reception_dashboard'))
        self.assertIn(res_guest.status_code, [302, 403])

        # Staff user succeeds
        self.client.force_login(self.staff_user)
        res_staff = self.client.get(reverse('reservations:reception_dashboard'))
        self.assertEqual(res_staff.status_code, 200)
        self.assertContains(res_staff, "Receptionist Dashboard")

    def test_complete_booking_approval_payment_and_confirmation_flow(self):
        """
        Tests the complete 8-step lifecycle:
        1. Guest submits request -> pending_review
        2. Staff sees it on dashboard
        3. Staff assigns physical room 101 and approves -> awaiting_payment
        4. Guest accesses secure payment link and uploads screenshot
        5. Staff reviews screenshot and verifies it -> verified
        6. Staff confirms reservation -> confirmed
        7. Room 101 is now blocked from duplicate overlapping approvals
        """
        # Step 1: Guest submits booking
        res = create_guest_reservation(
            guest_name="Almaz Ayana",
            email="almaz@example.com",
            phone="+251911554433",
            room_category=self.deluxe,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_guests=2,
        )
        self.assertEqual(res.status, ReservationStatus.PENDING_REVIEW)

        # Step 2: Staff logs in and views dashboard
        self.client.force_login(self.staff_user)
        dash_res = self.client.get(reverse('reservations:reception_dashboard'))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, res.reservation_reference)

        # Step 3: Staff opens reservation detail and approves, assigning Room 101
        detail_url = reverse('reservations:reception_detail', kwargs={'reservation_id': res.pk})
        detail_res = self.client.get(detail_url)
        self.assertEqual(detail_res.status_code, 200)

        approve_url = reverse('reservations:reception_approve', kwargs={'reservation_id': res.pk})
        approve_res = self.client.post(approve_url, data={
            'assigned_room': self.room_101.pk,
            'deadline_hours': 24,
        })
        self.assertRedirects(approve_res, detail_url)

        res.refresh_from_db()
        self.assertEqual(res.status, ReservationStatus.AWAITING_PAYMENT)
        self.assertEqual(res.assigned_room, self.room_101)
        self.assertIsNotNone(res.payment_deadline)

        # Step 4: Guest uploads payment screenshot via unguessable token
        guest_client = Client()
        upload_url = reverse('reservations:payment_upload', kwargs={'token': res.payment_upload_token})
        upload_get = guest_client.get(upload_url)
        self.assertEqual(upload_get.status_code, 200)
        self.assertContains(upload_get, "Room 101")
        self.assertContains(upload_get, res.reservation_reference)

        screenshot_file = SimpleUploadedFile("cbe_receipt.jpg", b"fake_bank_receipt_bytes", content_type="image/jpeg")
        upload_post = guest_client.post(upload_url, data={'screenshot': screenshot_file})
        self.assertRedirects(upload_post, upload_url)

        self.assertEqual(res.payment_proofs.count(), 1)
        proof = res.payment_proofs.first()
        self.assertEqual(proof.verification_status, PaymentVerificationStatus.PENDING)

        # Ensure uploading does NOT automatically confirm
        res.refresh_from_db()
        self.assertEqual(res.status, ReservationStatus.AWAITING_PAYMENT)

        # Step 5: Staff verifies payment proof
        verify_url = reverse('reservations:reception_verify_payment', kwargs={'proof_id': proof.pk})
        verify_res = self.client.post(verify_url, data={
            'verification_status': 'verified',
            'verification_notes': 'CBE Mobile Transfer #FT2611 verified.',
        })
        self.assertRedirects(verify_res, detail_url)

        proof.refresh_from_db()
        self.assertEqual(proof.verification_status, PaymentVerificationStatus.VERIFIED)
        self.assertEqual(proof.verified_by, self.staff_user)

        # Step 6: Staff confirms reservation
        confirm_url = reverse('reservations:reception_confirm', kwargs={'reservation_id': res.pk})
        confirm_res = self.client.post(confirm_url)
        self.assertRedirects(confirm_res, detail_url)

        res.refresh_from_db()
        self.assertEqual(res.status, ReservationStatus.CONFIRMED)

        # Step 7: Check that Room 101 cannot be assigned again for overlapping dates
        res_overlap = create_guest_reservation(
            guest_name="Overlapping Guest",
            email="overlap@example.com",
            phone="+251911999999",
            room_category=self.deluxe,
            check_in=self.check_in + timedelta(days=1),
            check_out=self.check_out + timedelta(days=1),
            number_of_guests=1,
        )
        # Attempt to assign Room 101 to res_overlap must fail
        with self.assertRaises(ValidationError):
            approve_reservation_and_assign_room(
                reservation_id=res_overlap.pk,
                room_id=self.room_101.pk,
                staff_user=self.staff_user,
            )
