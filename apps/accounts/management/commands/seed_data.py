from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.hashers import make_password
import random

from apps.accounts.models import User, UserActivity
from apps.posts.models import Category, CampusLocation, Post
from apps.membership.models import MembershipPlan, Membership
from apps.payments.models import Payment


class Command(BaseCommand):
    help = 'Seed database with initial data'

    def handle(self, *args, **options):
        self.stdout.write('Seeding data...')

        # Create admin
        if not User.objects.filter(username='admin').exists():
            admin = User.objects.create_superuser(
                username='admin',
                email='admin@iubat.edu',
                password='admin123',
                role='admin',
                student_id='ADMIN001',
                department='cse',
                phone='01700000000',
                is_verified=True,
                email_verified=True,
            )
            self.stdout.write('Admin created: admin / admin123')

        # Create categories
        categories = [
            ('Electronics', 'electronics', 'Laptops, phones, tablets, chargers, etc.', 'bi-phone'),
            ('Documents', 'documents', 'ID cards, certificates, notebooks, etc.', 'bi-file-text'),
            ('Accessories', 'accessories', 'Watches, glasses, jewelry, etc.', 'bi-watch'),
            ('Clothing', 'clothing', 'Jackets, bags, shoes, hats, etc.', 'bi-backpack'),
            ('Books', 'books', 'Textbooks, notebooks, study materials', 'bi-book'),
            ('Stationery', 'stationery', 'Pens, pencils, calculators, etc.', 'bi-pencil'),
            ('Money & Cards', 'money-cards', 'Cash, debit/credit cards, etc.', 'bi-wallet2'),
            ('Other', 'other', 'Miscellaneous items', 'bi-three-dots'),
        ]
        for name, slug, desc, icon in categories:
            Category.objects.get_or_create(name=name, slug=slug, defaults={'description': desc, 'icon': icon})

        # Campus Locations
        locations = [
            ('Academic Building A', 'academic-a', 'Main academic building', 'Academic Building A', 'Ground-5th'),
            ('Academic Building B', 'academic-b', 'Engineering building', 'Academic Building B', 'Ground-4th'),
            ('Library', 'library', 'Central library', 'Library Building', '1st-3rd'),
            ('Cafeteria', 'cafeteria', 'Main cafeteria', 'Student Center', 'Ground'),
            ('Student Center', 'student-center', 'Student activities center', 'Student Center', 'Ground-2nd'),
            ('Admin Building', 'admin-building', 'Administration office', 'Admin Building', 'Ground-3rd'),
            ('Medical Center', 'medical-center', 'University medical center', 'Medical Center', 'Ground'),
            ('Parking Area', 'parking-area', 'Vehicle parking area', 'Parking Lot', 'Ground'),
            ('Sports Complex', 'sports-complex', 'Indoor and outdoor sports', 'Sports Complex', 'Ground-2nd'),
            ('Boys Hostel', 'boys-hostel', 'Male student dormitory', 'Boys Hostel', 'Ground-5th'),
            ('Girls Hostel', 'girls-hostel', 'Female student dormitory', 'Girls Hostel', 'Ground-5th'),
        ]
        for name, slug, desc, building, floor in locations:
            CampusLocation.objects.get_or_create(name=name, slug=slug, defaults={'description': desc, 'building': building, 'floor': floor})

        # Membership Plan
        MembershipPlan.objects.get_or_create(
            name='Annual Membership',
            defaults={
                'price': 100,
                'duration_days': 365,
                'description': 'Full year membership with all features',
                'is_active': True,
            }
        )

        self.stdout.write(self.style.SUCCESS('Data seeded successfully!'))
