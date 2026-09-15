# IUBAT SmartFind — Practicum Defense Documentation

## Project Overview

**Name:** IUBAT SmartFind (LostFind)
**Type:** AI-Powered Lost & Found Management System
**Purpose:** IUBAT campus students যারা কিছু হারায় বা পায়, তাদের জন্য platform। AI দিয়ে automatically match করে, token-based verification দিয়ে জিনিস ফেরত দেওয়া হয়।

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.14 |
| Backend Framework | Django 6.0 |
| Database | PostgreSQL (Supabase) |
| AI Embeddings | Jina Embeddings API |
| Vector Search | pgvector (PostgreSQL extension) |
| Frontend | Tailwind CSS + Bootstrap Icons |
| Real-time Chat | Django Channels + WebSocket |
| Payment Gateway | SSLCommerz |
| Cache | Redis |
| Deployment | Heroku/Railway (Procfile) |

---

## Database Models & Relationships

### Core Models

```
User (accounts.User)
  ├── posts (Post)              <- User একাধিক post করতে পারে
  ├── membership (Membership)   <- User এর একটা membership থাকে
  ├── messages (Message)        <- User messages পাঠায়
  └── notifications (Notification)

Post (posts.Post)
  ├── user (FK -> User)          <- কে post করেছে
  ├── category (FK -> Category)  <- কোন category তে
  ├── location (FK -> CampusLocation) <- কোথায় হারালে/পেলে
  ├── images (PostImage)         <- একাধিক ছবি
  ├── tags (PostTag)             <- searchable tags
  ├── matched_post (FK -> self)  <- AI match এর সাথে link
  ├── embedding (PostEmbedding)  <- AI vector storage
  └── reports (TrustReport)      <- abuse reports
```

### Recovery Models

```
RecoverySession
  ├── post (FK -> Post)          <- কোন post এর জন্য
  ├── owner (FK -> User)         <- যে হারিয়েছে (token রাখে)
  ├── claimant (FK -> User)      <- যে পেয়েছে (token ঢোকায়)
  └── short_code                <- Recovery token (LF-XXXXXX)
```

### Payment Models

```
MembershipPlan
  ├── name, price, duration_days
  └── features (JSON)           <- কী কী feature পাবে

Payment
  ├── user (FK -> User)          <- কে payment করেছে
  ├── plan (FK -> MembershipPlan) <- কোন plan কিনেছে
  ├── amount, currency
  └── transaction_id             <- SSLCommerz transaction ID
```

---

## Feature Explanations

### 1. User Registration & Login

**Backend Flow:**
```
Register Form -> Django Form Validation -> User.save()
  -> role='student', membership_paid=False
  -> Auto login -> Redirect to membership purchase page

Login Form -> authenticate() -> check is_suspended
  -> check locked_until (brute-force protection)
  -> login(request, user) -> Reset failed_login_attempts
  -> Redirect based on role (admin/member)
```

**Database:**
- `User` model stores: username, email, password (hashed), role, department, is_membership_paid
- `UserActivity` logs every login/registration action

**Security:**
- Rate limiting: 5 attempts/min (register), 10 attempts/min (login)
- Brute-force lockout: 5 failed attempts -> 15 min lock
- Password reset token expires in 1 hour

---

### 2. Post Creation (Lost/Found)

**Backend Flow:**
```
Create Form -> PostForm.validate() -> Post.save()
  -> If lost post: create_recovery_session_for_post()
      -> RecoverySession.objects.create(short_code=generate_short_code())
  -> find_matches_for_post(post)
      -> build_text_for_post(post) -> "Lost: Blue phone Category: Electronics..."
      -> Jina API -> 256-dim vector -> Store in PostEmbedding
      -> Search pgvector for opposite-type posts -> Hybrid scoring -> Store MatchSuggestion
```

**Database:**
- `Post`: title, description, post_type (lost/found), status (open/claimed/resolved), image, contact_info
- `PostEmbedding`: OneToOne with Post, stores 256-dim vector for AI search
- `RecoverySession`: auto-created for lost posts with unique token

---

### 3. AI Matching System

**Backend Flow:**
```
Post Created/Edited
  -> build_text_for_post(post)   # "Lost: Blue phone Electronics Building 3..."
  -> Jina API (jina-embeddings-v5-text-nano) -> 256-dim vector
  -> Store in PostEmbedding table

Match Search:
  -> pgvector cosine distance search (opposite post type, active status)
  -> Top 20 candidates
  -> Hybrid scoring:
      Semantic: 60% (embedding similarity)
      Category: 15% (same category = bonus, different = penalty)
      Location: 10% (same location = bonus)
      Date: 10% (same day = 100%, decays to 0 over 14 days)
      Tags: 5% (Jaccard similarity)
  -> Score >= 40% -> Store MatchSuggestion
  -> Notify both users
```

**Database:**
- `PostEmbedding`: post (OneToOne), embedding (VectorField 256-dim)
- `MatchSuggestion`: post, matched_post, similarity_score, match_strength, status

---

### 4. Recovery Token System

**Backend Flow:**
```
Owner creates Lost Post
  -> RecoverySession created with token (e.g., LF-T2FJBL)
  -> Owner shares token with finder (in person or chat)

Finder enters token on Enter Token page
  -> Validate: token exists, session active, post not resolved
  -> Validate: involved users match (security check)
  -> Atomic transaction:
      -> Both sessions -> status='completed'
      -> Both posts -> status='resolved'
      -> Posts linked via matched_post field
      -> Notifications sent to both parties
```

**Session Status Flow:**
```
pending -> token_generated -> token_entered -> completed
                |                              |
            expired (30 days)              resolved
                |
            cancelled (by user/admin)
```

---

### 5. Real-time Chat (WebSocket)

**Backend Flow:**
```
User clicks "Start Conversation"
  -> start_conversation() view
  -> Find or create Conversation (participants + post)
  -> For lost posts: _initiate_recovery() -> create/link RecoverySession
  -> For found posts: _link_found_recovery() -> create/link RecoverySession
  -> Redirect to conversation page

WebSocket connection:
  -> ChatConsumer (Django Channels)
  -> connect() -> Join conversation group
  -> receive() -> Handle message types:
      - chat: Save message, broadcast to group
      - typing_start/typing_stop: Broadcast typing indicator
      - edit_message: Edit own message
      - delete_message: Soft-delete own message
```

**Database:**
- `Conversation`: participants (M2M), post (FK), subject
- `Message`: conversation (FK), sender (FK), body, is_read, is_deleted

---

### 6. Payment (SSLCommerz)

**Backend Flow:**
```
User clicks "Purchase Membership"
  -> Create Payment record (status='pending')
  -> SSLCommerz init_session() -> Get gateway URL
  -> Redirect to SSLCommerz payment page

After payment:
  -> SSLCommerz calls back (success/fail/cancel URLs)
  -> verify_sslcommerz_payment() -> Validate signature
  -> _validate_payment_result() -> Check amount, currency, transaction_id
  -> _complete_membership_payment() -> Activate membership
  -> Payment status -> 'completed'
  -> User.is_membership_paid = True
```

---

### 7. Admin Dashboard

**Admin capabilities:**
- Manage users (view, suspend, delete)
- Manage posts (view, edit, delete, moderate)
- Manage categories & locations
- View revenue & export to Excel
- Review trust reports
- Force-complete/cancel recovery sessions
- Reassign recovery claimants

---

### 8. Notifications

**Events that trigger notifications:**
- New match found -> "AI found a potential match!"
- Message received -> "New message from [user]"
- Recovery update -> "Finder assigned" / "Token entered"
- Post resolved -> "Item successfully recovered"

---

## Defense Talking Points

### Short Version (30 seconds)
> "SmartFind একটা AI-powered Lost & Found platform। হারানো জিনিস post করলে AI automatically match করবে পাওয়া জিনিসের সাথে। Recovery token দিয়ে verify করে জিনিসটা সত্যি তার। Real-time chat আছে, payment আছে SSLCommerz দিয়ে।"

### Medium Version (2 minutes)
> "IUBAT campusে যারা কিছু হারায় বা পায়, তাদের জন্য এই system। Owner lost post বানায়, finder found post বানায়। Jina AI API দিয়ে embedding generate হয়, pgvector দিয়ে cosine similarity search হয়। Match পেলে notification যায়। Chat করে, recovery token দিয়ে verify করে, জিনিস ফেরত পায়। SSLCommerz দিয়ে membership payment নেয়। PostgreSQL + Redis + Django Channels use করেছি।"

### Common Questions & Answers

**Q: AI কীভাবে match করে?**
> "Jina API দিয়ে post description কে 256-dim vector এ convert করে। pgvector দিয়ে opposite type posts এর সাথে cosine similarity বের করে। Hybrid scoring এ semantic 60%, category 15%, location 10%, date 10%, tags 5% weight। 40% এর বেশি হলে match suggestion দেখায়।"

**Q: Recovery token কীভাবে কাজ করে?**
> "Lost post বানালে auto-generated token তৈরি হয় (যেমন LF-T2FJBL)। Owner এই token finder কে দেয়। Finder enter token page তে ঢোকায়। Match হলে atomic transaction এ দুইটাই post resolved হয়।"

**Q: WebSocket কেন use করেছি?**
> "Real-time chat এর জন্য। Message পাঠালে তৎক্ষণাৎ দেখায়, page reload লাগে না। Django Channels + Redis backend use করেছি।"

**Q: Payment কীভাবে কাজ করে?**
> "SSLCommerz gateway use করেছি। Sandbox mode তে test করা হয়। User plan select করে, SSLCommerz page তে redirect হয়, payment করে, callback URL তে verify হয়, membership activate হয়।"

**Q: Admin panel তে কী আছে?**
> "User management, post moderation, revenue analytics, recovery session control, trust report review। Excel export আছে revenue data এর। Force-complete/cancel recovery করতে পারে।"

---

*Document prepared for IUBAT SmartFind Practicum Defense*
