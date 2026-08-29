import os
import secrets
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.hashers import make_password

from apps.accounts.models import User, UserActivity
from apps.posts.models import Category, CampusLocation, Post
from apps.membership.models import MembershipPlan, Membership
from apps.payments.models import Payment


class Command(BaseCommand):
    help = 'Seed database with initial data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--production',
            action='store_true',
            help='Skip admin user creation in production',
        )

    def handle(self, *args, **options):
        self.stdout.write('Seeding data...')
        is_production = options.get('production', False) or os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('PRODUCTION')

        # Create admin only in development
        if not is_production:
            if not User.objects.filter(username='admin').exists():
                admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
                admin = User.objects.create_superuser(
                    username='admin',
                    email='admin@iubat.edu',
                    password=admin_password,
                    role='admin',
                    student_id='ADMIN001',
                    department='cse',
                    phone='01700000000',
                    is_verified=True,
                    email_verified=True,
                )
                self.stdout.write(f'Admin created: admin / {admin_password}')
            else:
                self.stdout.write('Admin user already exists, skipping.')
        else:
            self.stdout.write('Production mode: ensuring admin password is set.')
            admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
            try:
                admin = User.objects.get(username='admin')
                admin.set_password(admin_password)
                admin.is_staff = True
                admin.is_superuser = True
                admin.role = 'admin'
                admin.is_verified = True
                admin.email_verified = True
                admin.is_active = True
                admin.save()
                self.stdout.write(f'Admin password reset: admin / {admin_password}')
            except User.DoesNotExist:
                admin = User.objects.create_superuser(
                    username='admin',
                    email='admin@iubat.edu',
                    password=admin_password,
                    role='admin',
                    student_id='ADMIN001',
                    department='cse',
                    phone='01700000000',
                    is_verified=True,
                    email_verified=True,
                )
                self.stdout.write(f'Admin created: admin / {admin_password}')

        # Create test users (both dev and production)
        test_users = [
            {
                'username': 'Harun',
                'email': 'harun@iubat.edu',
                'password': 'h@run123',
                'first_name': 'Harun',
                'last_name': 'Rahman',
                'role': 'student',
                'student_id': 'IUBAT-001',
                'department': 'cse',
                'phone': '01712345678',
            },
            {
                'username': 'Rafid',
                'email': 'rafid@iubat.edu',
                'password': 'rafid123',
                'first_name': 'Rafid',
                'last_name': 'Ahmed',
                'role': 'student',
                'student_id': 'IUBAT-002',
                'department': 'cse',
                'phone': '01712345679',
            },
            {
                'username': 'Tanmoy',
                'email': 'tanmoy@iubat.edu',
                'password': 'tanmoy123',
                'first_name': 'Tanmoy',
                'last_name': 'Das',
                'role': 'student',
                'student_id': 'IUBAT-003',
                'department': 'cse',
                'phone': '01712345680',
            },
        ]

        plan = MembershipPlan.objects.first()
        for u in test_users:
            user, created = User.objects.get_or_create(
                username=u['username'],
                defaults={
                    'email': u['email'],
                    'first_name': u['first_name'],
                    'last_name': u['last_name'],
                    'role': u['role'],
                    'student_id': u['student_id'],
                    'department': u['department'],
                    'phone': u['phone'],
                    'is_verified': True,
                    'email_verified': True,
                    'is_membership_paid': True,
                },
            )
            user.set_password(u['password'])
            user.is_verified = True
            user.email_verified = True
            user.is_membership_paid = True
            user.is_active = True
            user.save()
            Membership.objects.get_or_create(
                user=user,
                defaults={
                    'plan': plan,
                    'is_active': True,
                    'started_at': timezone.now(),
                    'expires_at': timezone.now() + timedelta(days=365),
                },
            )
            action = 'created' if created else 'password reset'
            self.stdout.write(f"User {action}: {u['username']} / {u['password']}")

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
