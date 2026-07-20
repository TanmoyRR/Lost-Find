import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

User = get_user_model()

# ========================
# AUTHENTICATION & ACCOUNTS
# ========================

class TestRegistration(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('accounts:register')

    def test_registration_page_loads(self):
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/register.html')

    def test_user_can_register(self):
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
            'student_id': '2021-001-001',
            'department': 'cse',
            'phone': '01700000000',
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='testuser').exists())

    def test_registration_requires_unique_username(self):
        User.objects.create_user(username='testuser', password='test123')
        data = {
            'username': 'testuser',
            'email': 'test2@example.com',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')

    def test_registration_requires_matching_passwords(self):
        data = {
            'username': 'testuser2',
            'email': 'test2@example.com',
            'password1': 'ComplexPass123!',
            'password2': 'DifferentPass456!',
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'match')

    def test_blank_student_id_allowed(self):
        data = {
            'username': 'testuser3',
            'email': 'test3@example.com',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
            'student_id': '',
            'department': 'cse',
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, 302)


class TestLogin(TestCase):
    def setUp(self):
        self.client = Client()
        self.login_url = reverse('accounts:login')
        self.user = User.objects.create_user(username='testuser', password='testpass123', email='test@example.com')

    def test_login_page_loads(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)

    def test_user_can_login(self):
        response = self.client.post(self.login_url, {'username': 'testuser', 'password': 'testpass123'})
        self.assertEqual(response.status_code, 302)

    def test_login_with_invalid_credentials_fails(self):
        response = self.client.post(self.login_url, {'username': 'testuser', 'password': 'wrongpass'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter')

    def test_suspended_user_cannot_login(self):
        self.user.is_suspended = True
        self.user.save()
        response = self.client.post(self.login_url, {'username': 'testuser', 'password': 'testpass123'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'suspended')


class TestPermissions(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='regular', password='testpass')
        self.admin = User.objects.create_superuser(username='admin', email='admin@test.com', password='adminpass')
        self.admin.role = 'admin'
        self.admin.save()

    def test_unauthenticated_redirected_to_login(self):
        protected_urls = ['dashboard:home', 'accounts:profile', 'accounts:edit_profile']
        for url_name in protected_urls:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 302)

    def test_admin_dashboard_requires_admin(self):
        self.client.login(username='regular', password='testpass')
        response = self.client.get(reverse('dashboard:admin_home'))
        self.assertEqual(response.status_code, 302)

    def test_admin_dashboard_allows_admin(self):
        self.client.login(username='admin', password='adminpass')
        response = self.client.get(reverse('dashboard:admin_home'))
        self.assertEqual(response.status_code, 200)


# ========================
# POST LIFECYCLE
# ========================

class TestPostLifecycle(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='poster', password='testpass')
        self.client.login(username='poster', password='testpass')
        from apps.posts.models import Category, CampusLocation
        self.category = Category.objects.create(name='Electronics', slug='electronics')
        self.location = CampusLocation.objects.create(name='Building A', slug='building-a')
        self.create_url = reverse('posts:create')

    def test_create_page_loads(self):
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)

    def test_user_can_create_lost_post(self):
        data = {
            'title': 'Lost iPhone',
            'description': 'Black iPhone 14 in Building A',
            'post_type': 'lost',
            'category': self.category.pk,
            'location': self.location.pk,
            'date_lost_found': timezone.now().date(),
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, 302)
        from apps.posts.models import Post
        self.assertTrue(Post.objects.filter(title='Lost iPhone').exists())

    def test_user_can_create_found_post(self):
        data = {
            'title': 'Found Keys',
            'description': 'Found a set of keys near the library',
            'post_type': 'found',
            'category': self.category.pk,
            'location': self.location.pk,
            'date_lost_found': timezone.now().date(),
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, 302)
        from apps.posts.models import Post
        self.assertTrue(Post.objects.filter(title='Found Keys').exists())

    def test_user_cannot_create_post_with_blank_title(self):
        data = {
            'title': '',
            'description': 'Some description',
            'post_type': 'lost',
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'required')

    def test_user_can_edit_own_post(self):
        from apps.posts.models import Post
        post = Post.objects.create(
            user=self.user, title='Original Title', description='Test',
            post_type='lost', date_lost_found=timezone.now().date()
        )
        edit_url = reverse('posts:edit', kwargs={'pk': post.pk})
        response = self.client.post(edit_url, {
            'title': 'Updated Title',
            'description': 'Updated description',
            'post_type': 'lost',
            'category': self.category.pk,
            'location': self.location.pk,
            'date_lost_found': timezone.now().date(),
        })
        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertEqual(post.title, 'Updated Title')

    def test_user_can_delete_own_post(self):
        from apps.posts.models import Post
        post = Post.objects.create(
            user=self.user, title='To Delete', description='Test',
            post_type='lost', date_lost_found=timezone.now().date()
        )
        delete_url = reverse('posts:delete', kwargs={'pk': post.pk})
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())

    def test_user_can_mark_resolved(self):
        from apps.posts.models import Post
        post = Post.objects.create(
            user=self.user, title='Resolve Me', description='Test',
            post_type='lost', date_lost_found=timezone.now().date()
        )
        resolve_url = reverse('posts:resolve', kwargs={'pk': post.pk})
        response = self.client.post(resolve_url)
        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertEqual(post.status, 'resolved')
        self.assertTrue(post.is_resolved)

    def test_user_cannot_edit_anothers_post(self):
        other_user = User.objects.create_user(username='other', password='testpass')
        from apps.posts.models import Post
        post = Post.objects.create(
            user=other_user, title='Others Post', description='Test',
            post_type='lost', date_lost_found=timezone.now().date()
        )
        edit_url = reverse('posts:edit', kwargs={'pk': post.pk})
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 404)


# ========================
# BROWSE & SEARCH
# ========================

class TestBrowseAndSearch(TestCase):
    def setUp(self):
        self.client = Client()
        from apps.posts.models import Post, Category, CampusLocation
        self.cat = Category.objects.create(name='Books', slug='books')
        self.loc = CampusLocation.objects.create(name='Library', slug='library')
        self.user = User.objects.create_user(username='browser', password='testpass')
        for i in range(15):
            Post.objects.create(
                user=self.user, title=f'Test Post {i}', description=f'Description {i}',
                post_type='lost' if i % 2 == 0 else 'found',
                category=self.cat if i < 10 else None,
                location=self.loc if i < 10 else None,
                date_lost_found=timezone.now().date(),
            )

    def test_browse_page_loads(self):
        response = self.client.get(reverse('posts:browse'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Post')

    def test_browse_filters_by_type(self):
        response = self.client.get(reverse('posts:browse') + '?type=lost')
        self.assertEqual(response.status_code, 200)

    def test_browse_has_pagination(self):
        response = self.client.get(reverse('posts:browse'))
        self.assertContains(response, 'page')

    def test_post_detail_shows(self):
        from apps.posts.models import Post
        post = Post.objects.first()
        response = self.client.get(reverse('posts:detail', kwargs={'pk': post.pk}))
        self.assertEqual(response.status_code, 200)


# ========================
# MATCHING ENGINE
# ========================

class TestMatchingEngine(TestCase):
    def setUp(self):
        from apps.posts.models import Post, Category, CampusLocation
        self.user = User.objects.create_user(username='matcher', password='testpass')
        self.cat = Category.objects.create(name='Electronics', slug='electronics')
        self.loc = CampusLocation.objects.create(name='Campus A', slug='campus-a')
        self.lost_post = Post.objects.create(
            user=self.user, title='Lost Phone', description='Black Samsung phone',
            post_type='lost', category=self.cat, location=self.loc,
            date_lost_found=timezone.now().date(),
        )
        self.found_post = Post.objects.create(
            user=self.user, title='Found Phone', description='Found a black Samsung',
            post_type='found', category=self.cat, location=self.loc,
            date_lost_found=timezone.now().date(),
        )

    @patch('apps.ai_engine.utils.generate_embedding')
    @patch('apps.ai_engine.utils.compute_cosine_similarity')
    def test_match_created_on_post_creation(self, mock_similarity, mock_embedding):
        mock_embedding.return_value = [0.1] * 384
        mock_similarity.return_value = 0.85
        from apps.ai_engine.utils import find_matches_for_post
        matches = find_matches_for_post(self.lost_post)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].similarity_score, 1.0)

    def test_match_suggestion_page_requires_login(self):
        response = self.client.get(reverse('ai:matches'))
        self.assertEqual(response.status_code, 302)

    def test_match_suggestion_page_works(self):
        from apps.ai_engine.models import MatchSuggestion
        MatchSuggestion.objects.create(post=self.lost_post, matched_post=self.found_post, similarity_score=0.9)
        self.client.login(username='matcher', password='testpass')
        response = self.client.get(reverse('ai:matches'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Lost Phone')

    def test_dismiss_match(self):
        from apps.ai_engine.models import MatchSuggestion
        match = MatchSuggestion.objects.create(post=self.lost_post, matched_post=self.found_post, similarity_score=0.9)
        self.client.login(username='matcher', password='testpass')
        response = self.client.get(reverse('ai:dismiss_match', kwargs={'match_id': match.pk}))
        self.assertEqual(response.status_code, 302)
        match.refresh_from_db()
        self.assertEqual(match.status, 'dismissed')

    def test_accept_match(self):
        from apps.ai_engine.models import MatchSuggestion
        match = MatchSuggestion.objects.create(post=self.lost_post, matched_post=self.found_post, similarity_score=0.9)
        self.client.login(username='matcher', password='testpass')
        response = self.client.get(reverse('ai:accept_match', kwargs={'match_id': match.pk}))
        self.assertEqual(response.status_code, 302)
        match.refresh_from_db()
        self.assertEqual(match.status, 'accepted')
        self.assertTrue(match.is_accepted)


# ========================
# MEMBERSHIP SYSTEM
# ========================

class TestMembership(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='member', password='testpass')
        self.client.login(username='member', password='testpass')
        from apps.membership.models import MembershipPlan
        self.plan = MembershipPlan.objects.create(
            name='Premium Monthly', price=Decimal('50.00'), duration_days=30, is_active=True
        )

    def test_membership_page_loads(self):
        response = self.client.get(reverse('membership:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Premium Monthly')

    def test_purchase_initiation_creates_membership(self):
        response = self.client.get(reverse('membership:purchase', kwargs={'plan_id': self.plan.pk}))
        self.assertEqual(response.status_code, 302)
        from apps.membership.models import Membership
        self.assertTrue(Membership.objects.filter(user=self.user).exists())

    def test_membership_success_page(self):
        from apps.membership.models import Membership
        Membership.objects.create(
            user=self.user, plan=self.plan, is_active=True,
            started_at=timezone.now(), expires_at=timezone.now() + timedelta(days=30)
        )
        response = self.client.get(reverse('membership:success'))
        self.assertEqual(response.status_code, 200)


# ========================
# PAYMENTS / SSLCOMMERZ
# ========================

class TestPayments(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='payer', password='testpass')
        self.client.login(username='payer', password='testpass')

    @patch('apps.payments.views.initiate_payment')
    def test_payment_initiation(self, mock_initiate):
        mock_initiate.return_value = 'http://mock-gateway-url.com'
        response = self.client.get(reverse('membership:index'))
        self.assertEqual(response.status_code, 200)

    def test_payment_success_callback(self):
        from apps.payments.models import Payment
        from apps.membership.models import MembershipPlan, Membership
        plan = MembershipPlan.objects.create(name='Test', price=Decimal('100'), duration_days=30)
        payment = Payment.objects.create(
            user=self.user, transaction_id='TXN123', amount=Decimal('100.00'),
            payment_type='membership', status='pending',
        )
        response = self.client.post(reverse('payments:success'), {
            'tran_id': 'TXN123',
            'status': 'VALID',
            'val_id': 'VAL001',
        })
        self.assertEqual(response.status_code, 302)


# ========================
# ADMIN MODERATION
# ========================

class TestAdminModeration(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(username='admin', email='admin@test.com', password='adminpass')
        self.admin.role = 'admin'
        self.admin.save()
        self.client.login(username='admin', password='adminpass')

    def test_admin_dashboard_loads(self):
        response = self.client.get(reverse('dashboard:admin_home'))
        self.assertEqual(response.status_code, 200)

    def test_admin_users_page(self):
        response = self.client.get(reverse('dashboard:admin_users'))
        self.assertEqual(response.status_code, 200)

    def test_admin_posts_page(self):
        response = self.client.get(reverse('dashboard:admin_posts'))
        self.assertEqual(response.status_code, 200)

    def test_admin_categories_page(self):
        response = self.client.get(reverse('dashboard:admin_categories'))
        self.assertEqual(response.status_code, 200)

    def test_admin_locations_page(self):
        response = self.client.get(reverse('dashboard:admin_locations'))
        self.assertEqual(response.status_code, 200)

    def test_admin_payments_page(self):
        response = self.client.get(reverse('dashboard:admin_payments'))
        self.assertEqual(response.status_code, 200)

    def test_admin_reports_page(self):
        response = self.client.get(reverse('dashboard:admin_reports'))
        self.assertEqual(response.status_code, 200)

    def test_admin_analytics_page(self):
        response = self.client.get(reverse('dashboard:admin_analytics'))
        self.assertEqual(response.status_code, 200)

    def test_admin_suspend_user(self):
        user = User.objects.create_user(username='suspendeduser', password='testpass')
        suspend_url = reverse('dashboard:admin_suspend_user', kwargs={'pk': user.pk})
        response = self.client.get(suspend_url)
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_suspended)

    def test_admin_activate_user(self):
        user = User.objects.create_user(username='activeuser', password='testpass', is_suspended=True)
        activate_url = reverse('dashboard:admin_activate_user', kwargs={'pk': user.pk})
        response = self.client.get(activate_url)
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertFalse(user.is_suspended)


# ========================
# API TESTS
# ========================

class TestAPIs(TestCase):
    def setUp(self):
        self.client = Client()
        from apps.posts.models import Post, Category
        self.user = User.objects.create_user(username='apiuser', password='testpass')
        self.cat = Category.objects.create(name='TestCat', slug='testcat')
        Post.objects.create(
            user=self.user, title='API Post', description='Test',
            post_type='lost', category=self.cat,
            date_lost_found=timezone.now().date(),
        )

    def test_api_posts_returns_json(self):
        response = self.client.get(reverse('posts:api_posts'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_api_posts_filters_by_type(self):
        response = self.client.get(reverse('posts:api_posts') + '?type=lost')
        self.assertEqual(response.status_code, 200)
        import json
        data = json.loads(response.content)
        self.assertEqual(len(data['posts']), 1)


# ========================
# NOTIFICATIONS
# ========================

class TestNotifications(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='notifuser', password='testpass')
        self.client.login(username='notifuser', password='testpass')
        from apps.notifications.models import Notification
        Notification.objects.create(
            user=self.user, notification_type='system',
            title='Test Notification', message='This is a test'
        )

    def test_notification_list_loads(self):
        response = self.client.get(reverse('notifications:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Notification')

    def test_mark_all_read_works(self):
        response = self.client.get(reverse('notifications:mark_all_read'))
        self.assertEqual(response.status_code, 302)
        from apps.notifications.models import Notification
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 0)


# ========================
# SUCCESS STORIES
# ========================

class TestSuccessStories(TestCase):
    def setUp(self):
        self.client = Client()
        from apps.posts.models import Post, SuccessStory
        self.user = User.objects.create_user(username='storyuser', password='testpass')
        post = Post.objects.create(
            user=self.user, title='Story Post', description='Test',
            post_type='found', date_lost_found=timezone.now().date()
        )
        SuccessStory.objects.create(
            post=post, title='Great Story', story='Someone found an item!',
            finder_name='Finder', owner_name='Owner', is_published=True
        )

    def test_success_stories_page_loads(self):
        response = self.client.get(reverse('posts:success_stories'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Great Story')


# ========================
# TRUST & SAFETY
# ========================

class TestTrustSafety(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='reporter', password='testpass')
        self.client.login(username='reporter', password='testpass')
        from apps.posts.models import Post
        self.post = Post.objects.create(
            user=self.user, title='Reportable Post', description='Test',
            post_type='lost', date_lost_found=timezone.now().date()
        )

    def test_report_page_loads(self):
        response = self.client.get(reverse('posts:report_item', kwargs={'post_id': self.post.pk}))
        self.assertEqual(response.status_code, 200)

    def test_report_submission_works(self):
        response = self.client.post(
            reverse('posts:report_item', kwargs={'post_id': self.post.pk}),
            {'report_type': 'spam', 'description': 'This is spam'}
        )
        self.assertEqual(response.status_code, 302)
        from apps.posts.models import TrustReport
        self.assertTrue(TrustReport.objects.filter(post=self.post).exists())


# ========================
# RECOVERY SYSTEM
# ========================

class TestRecoverySystem(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(username='owner', password='testpass')
        self.claimant = User.objects.create_user(username='claimant', password='testpass')
        from apps.posts.models import Post
        self.post = Post.objects.create(
            user=self.owner, title='Recoverable Item', description='Test',
            post_type='lost', date_lost_found=timezone.now().date()
        )

    def test_initiate_recovery_requires_login(self):
        response = self.client.get(reverse('recovery:initiate', kwargs={'post_id': self.post.pk}))
        self.assertEqual(response.status_code, 302)

    def test_initiate_recovery_works(self):
        self.client.login(username='claimant', password='testpass')
        response = self.client.get(reverse('recovery:initiate', kwargs={'post_id': self.post.pk}))
        self.assertEqual(response.status_code, 302)
        from apps.recovery.models import RecoverySession
        self.assertTrue(RecoverySession.objects.filter(post=self.post, claimant=self.claimant).exists())

    def test_cannot_initiate_own_post(self):
        self.client.login(username='owner', password='testpass')
        response = self.client.get(reverse('recovery:initiate', kwargs={'post_id': self.post.pk}))
        self.assertEqual(response.status_code, 302)
        from django.contrib.messages import get_messages
        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('cannot claim' in str(m).lower() for m in msgs))

    def test_recovery_list_works(self):
        self.client.login(username='owner', password='testpass')
        response = self.client.get(reverse('recovery:list'))
        self.assertEqual(response.status_code, 200)