\# IUBAT SmartFind: AI-Powered Lost \& Found System (SRS)



\## Software Requirements Specification (SRS)



\---



\# Project Overview



Lost \& Found Board System is a web-based platform designed to help users report, search, match, and recover lost or found items efficiently.



The platform aims to create a trusted and verified community by combining:



\* Membership-based participation

\* AI-powered semantic search

\* Automatic lost/found matching

\* OTP verification

\* QR-based recovery confirmation

\* Administrative moderation



The system will prioritize trust, security, usability, and recovery success.



\---



\# 1. Objectives



The system aims to:



\* Allow users to report lost items.

\* Allow users to report found items.

\* Help users locate matching items through AI-assisted search.

\* Automatically suggest potential matches.

\* Verify ownership securely before recovery.

\* Reduce fraud and spam through membership restrictions.

\* Provide administrators with moderation and management tools.

\* Deliver a professional and responsive user experience.



\---



\# 2. User Roles



\## 2.1 Guest User



Guest users can:



\* View public lost item posts.

\* View public found item posts.

\* Search and browse listings.

\* Register an account.



Guest users cannot:



\* Create posts.

\* Contact users.

\* Initiate recovery requests.

\* Access verification features.



\---



\## 2.2 Registered User (Without Membership)



Users can register an account for free.



Registered users can:



\* Login and logout.

\* Browse public posts.

\* Search listings.

\* Manage profile information.



Registered users cannot:



\* Create lost posts.

\* Create found posts.

\* Contact owners.

\* Contact finders.

\* Initiate recovery requests.

\* Use OTP verification.

\* Use QR verification.



\---



\## 2.3 Active Member



Full platform participation requires an active membership.



\### Membership Details



\* Membership Fee: 100 BDT per year.

\* Membership Duration: 1 Year.

\* Membership Renewal Required Annually.



Active members can:



\* Create Lost Posts.

\* Create Found Posts.

\* Edit Own Posts.

\* Delete Own Posts.

\* Contact Owners.

\* Contact Finders.

\* Receive AI Match Suggestions.

\* Initiate Recovery Requests.

\* Use OTP Verification.

\* Use QR Recovery Confirmation.



\---



\## 2.4 Administrator



Administrators have unrestricted access.



Administrators can:



\* Manage Users.

\* Manage Memberships.

\* Manage Posts.

\* Manage Categories.

\* Manage Locations.

\* Moderate Content.

\* Review Recovery Logs.

\* Access Analytics Dashboard.



\### Administrator Membership Policy



\* Administrators do not require membership.

\* Membership restrictions never apply to administrators.

\* All administrator functions remain permanently available.



\---



\# 3. Authentication System



\## Features



\* User Registration

\* User Login

\* User Logout

\* Password Reset

\* Role-Based Access Control

\* Session Management



\---



\# 4. Membership System



\## Overview



The platform operates using a yearly membership model to maintain a trusted and verified user community.



\### Membership Information



The system must track:



\* Membership ID

\* Membership Status

\* Membership Start Date

\* Membership Expiration Date



\### Membership Status



\* Active

\* Expired

\* Pending Payment



\### Membership Restrictions



Users without an active membership cannot:



\* Create Posts

\* Contact Other Users

\* Initiate Recovery Requests

\* Access Verification Features



Users without membership can still:



\* Browse Posts

\* Search Listings

\* Manage Their Profile



\---



\# 5. User Profile System



\## User Profile Contains



\* Profile Picture

\* Full Name

\* Email Address

\* Phone Number

\* Membership Status

\* Membership Expiration Date

\* Account Creation Date

\* Recovery Statistics

\* Activity Summary



\## Profile Features



\* Edit Profile

\* Change Password

\* View My Posts

\* View Recovery History



\---



\# 6. Lost Item Module



Users can create lost item posts containing:



\* Item Name

\* Category

\* Description

\* Last Seen Location

\* Lost Date

\* Images



\## Available Actions



\* Create Post

\* Edit Post

\* Delete Post

\* Mark as Recovered



\---



\# 7. Found Item Module



Users can create found item posts containing:



\* Item Name

\* Category

\* Description

\* Found Location

\* Found Date

\* Images



\## Available Actions



\* Create Post

\* Edit Post

\* Delete Post

\* Mark as Returned



\---



\# 8. Search System



\## Basic Search



\* Keyword Search

\* Category Search

\* Location Search



\## Advanced Filters



\* Lost Items Only

\* Found Items Only

\* Category Filter

\* Date Filter

\* Status Filter



\## Dynamic Search



Search results must update dynamically without full page reloads.



Possible implementation:



\* AJAX

\* HTMX

\* Fetch API



\---



\# 9. AI Smart Search



Implement semantic search using:



\* Sentence Transformers

\* Embeddings

\* Cosine Similarity



The system should:



\* Understand meaning instead of exact keywords.

\* Return relevant results for similar descriptions.

\* Improve search accuracy.



Example:



Lost Post:



"Black leather wallet"



Search Query:



"Dark colored purse"



The system should identify this as a possible match.



\---



\# 10. Automatic Matching System



\## Match Generation



After creating a Lost or Found post, the system automatically compares:



\* Item Title

\* Category

\* Description

\* Location

\* Date Information



\## Match Suggestions



Display:



\* Potential Matches

\* Similar Posts

\* Similarity Percentage

\* Match Confidence Score



\---



\# 11. Recovery Request System



\## Recovery Workflow



1\. Owner and Finder establish contact.

2\. Recovery Request is created.

3\. OTP Verification begins.

4\. QR Verification begins.

5\. Recovery is confirmed.

6\. Item status becomes Recovered.



\## Recovery Status



\* Pending

\* OTP Generated

\* OTP Verified

\* QR Generated

\* QR Verified

\* Recovered



The system must maintain a complete recovery log.



\---



\# 12. QR Recovery Verification System



\## Purpose



Provide additional proof of successful recovery.



\## Flow



1\. QR Generated.

2\. Authorized User Scans QR.

3\. Verification Completed.

4\. Recovery Finalized.



\## Requirements



\* Unique QR Code

\* One-Time Usage

\* Expiration Support

\* Verification Logs



\---



\# 13. Notification System



Future Enhancements:



\* Email Notifications

\* Match Alerts

\* Recovery Notifications

\* Membership Expiry Notifications

\* Administrative Notifications



\---



\# 14. Admin Dashboard



\## Dashboard Statistics



\* Total Users

\* Active Members

\* Expired Memberships

\* Lost Posts

\* Found Posts

\* Recoveries



\---



\## User Management



\* View Users

\* Suspend Users

\* Delete Users



\---



\## Membership Management



\* View Memberships

\* Activate Memberships

\* Renew Memberships

\* Expire Memberships



\---



\## Post Management



\* Review Posts

\* Moderate Posts

\* Remove Posts

\* Handle Reports



\---



\## Category Management



\* Add Categories

\* Edit Categories

\* Delete Categories



\---



\## Location Management



\* Add Locations

\* Edit Locations

\* Delete Locations



\---



\## Recovery Management



\* View Recovery Requests

\* View OTP Logs

\* View QR Logs



\---



\# 15. UI/UX Requirements



\## Design Style



Modern Dashboard-Based Interface



\## Layout Requirements



\* Left Sidebar Navigation

\* Responsive Design

\* Mobile Friendly Layout

\* Consistent Design System



\## Sidebar Menu



\* Dashboard

\* Lost Items

\* Found Items

\* Create Post

\* My Posts

\* Profile

\* Settings



\## Design Goals



\* Clean

\* Professional

\* Accessible

\* Easy Navigation

\* Consistent User Experience



\---



\# 16. Non-Functional Requirements



\## Performance



\* Fast Search Response

\* Optimized Database Queries

\* Efficient Image Loading



\## Security



\* Authentication Protection

\* Authorization Validation

\* Membership Access Control

\* CSRF Protection

\* Secure File Upload

\* OTP Security

\* QR Security



\## Reliability



\* Recovery Logging

\* Error Handling

\* Input Validation



\## Scalability



\* Modular Architecture

\* Future Payment Integration Support

\* Future Mobile App Support



\---



\# 17. Payment System



\## Current Version



For academic development and demonstration:



\* Simulated Payment Flow

\* Manual Membership Activation Allowed

\* Demo Transaction Records



No live payment gateway integration is required.



\---



\## Future Version



Planned Features:



\* SSLCommerz Integration

\* Membership Purchase

\* Membership Renewal

\* Transaction History

\* Payment Verification



\---



\# 18. Technology Stack



\## Frontend



\* HTML

\* Tailwind CSS

\* JavaScript



\## Backend



\* Django



\## Database



\* PostgreSQL / Supabase



\## AI Components



\* Sentence Transformers

\* Cosine Similarity Matching



\---



\# 19. Version 1.0 Scope



The first release must include:



\* Authentication System

\* Membership System

\* User Profiles

\* Lost Item Management

\* Found Item Management

\* Smart Search

\* AI Matching Suggestions

\* Recovery Request System

\* OTP Verification

\* QR Verification

\* Admin Dashboard

\* Membership Management

\* Responsive UI



\---





\# 20. Direct Messaging System



\## Overview



The platform shall provide a secure real-time messaging system that allows users to communicate directly regarding a lost or found item.



The messaging system is intended solely for item recovery discussions and must remain private between the involved users.



\---



\## Chat Eligibility



Only authenticated users with an active membership can initiate conversations.



A chat can only be started when:



\* A user has created a Lost Item post and wants to contact the owner of a matching Found Item post.

\* A user has created a Found Item post and wants to communicate with the owner of a matching Lost Item post.



Guests and users without an active membership cannot initiate conversations.



\---



\## Chat Features



Each conversation shall support:



\* One-to-One Messaging

\* Real-Time Message Updates

\* Text Messages

\* Timestamp for Every Message

\* Read / Unread Status

\* Conversation History

\* Auto Scroll to Latest Message

\* Responsive Chat Interface



\---



\## Chat Security



The system must ensure:



\* Only the two participants can access the conversation.

\* Users cannot access conversations they are not part of.

\* Messages remain private.

\* Authorization checks on every request.



\---



\## Chat Window



The interface should include:



\* User Name

\* Profile Picture

\* Item Reference

\* Online / Offline Status (Optional)

\* Message Input Box

\* Send Button

\* Message Timestamp



\---



\## Conversation Management



Users should be able to:



\* View Previous Conversations

\* Continue Existing Conversations

\* Delete Their Own Conversation History (Optional)



\---



\## Recovery Integration



Once both users agree to recover the item, either participant can initiate a Recovery Request directly from the chat interface.



The chat should include a prominent "Start Recovery" button.



\---



\## Notifications (Future Enhancement)



Future versions may support:



\* Real-Time Notifications

\* Desktop Notifications

\* Email Notifications

\* Push Notifications



\---



\## Technical Recommendation



Suggested implementation:



\* Django Channels

\* WebSockets

\* Redis (Optional)



If WebSockets are unavailable, implement AJAX polling as a fallback.







\# 21. Future Enhancements



\* SSLCommerz Live Integration

\* Reward System

\* Commission System

\* AI Image Matching

\* Fraud Detection System

\* Mobile Application

\* Push Notifications

\* Advanced Analytics

