#!/usr/bin/env python3
"""
Generate synthetic seed data for ResolveAI.

Default mode: deterministic template-based generation (no API key needed).
LLM mode   : --use-llm — calls OpenAI to produce richer, varied content.

Usage:
    python scripts/generate_synthetic_data.py            # local templates
    python scripts/generate_synthetic_data.py --use-llm  # OpenAI-enhanced
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "seed"
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "policy_docs").mkdir(exist_ok=True)

# ── personal data pools (all obviously fake) ─────────────────────────────────
FIRST_NAMES = [
    "Ahmed", "Ali", "Usman", "Hassan", "Bilal", "Imran", "Zain", "Faisal",
    "Omar", "Hamza", "Ayesha", "Fatima", "Zara", "Sara", "Nadia", "Hina",
    "Sana", "Maryam", "Amna", "Rabia", "Tariq", "Asif", "Kamran", "Waqar",
    "Saad", "Adnan", "Raza", "Junaid", "Babar", "Shahid",
]
LAST_NAMES = [
    "Khan", "Ahmed", "Ali", "Sheikh", "Qureshi", "Malik", "Siddiqui",
    "Chaudhry", "Mirza", "Butt", "Akhtar", "Hussain", "Ansari", "Rehman",
    "Iqbal", "Javed", "Nawaz", "Niazi", "Abbasi", "Zaidi",
]
CITIES = ["Karachi", "Lahore", "Islamabad", "Rawalpindi", "Faisalabad",
          "Multan", "Peshawar", "Quetta", "Hyderabad", "Sialkot"]

# ── article generation ────────────────────────────────────────────────────────

_ARTICLE_TEMPLATE = """\
{title}

{title} is an important part of the {area} experience at ResolveAI. \
Customers frequently ask about {topic_lower} and how to manage it on our platform. \
This guide provides a clear, step-by-step explanation to help you navigate \
{topic_lower} smoothly and efficiently.

{detail}

How to Proceed

The process begins by logging into your ResolveAI account. Navigate to the \
relevant {area} section in your dashboard. Look for the option that relates to \
{topic_lower} and follow the on-screen prompts. Our interface is designed to \
guide you through each required step with clear instructions and real-time \
feedback. Most actions can be completed in under two minutes.

Where required, you may need to provide your order or transaction reference \
number, a description of the issue, and any supporting photos or documents. \
Our system validates submissions instantly and provides a confirmation reference.

Status Updates and Timeline

After initiating a {topic_lower} request, you will receive a confirmation via \
SMS to your registered mobile number and an email to your registered address. \
The timeline depends on the nature of the request: routine matters are resolved \
within 24 hours, while complex cases may take 3-5 business days. Our support \
team will keep you informed at each stage.

For time-sensitive {area} matters, use the Priority flag available to Standard \
and Premium tier customers. Premium customers are guaranteed a response within \
one business hour, even on weekends and public holidays.

Common Questions

Q: What if my {topic_lower} request is rejected?
A: You will receive a reason via SMS and email. You can resubmit after \
addressing the issue or contact our support team to dispute the decision.

Q: Can I track the progress of my {topic_lower} request?
A: Yes. Log into your account and navigate to the {area} section to see \
real-time status updates for all pending requests.

Q: Is there a deadline for submitting a {topic_lower} request?
A: Deadlines vary by request type. For most {area} matters, requests must be \
submitted within 30 days of the relevant event. Check our policy page for \
specific deadlines.

Contact and Support

For assistance with {topic_lower}, our dedicated {area} support team is \
available around the clock. Reach us via WhatsApp at our business number, \
through live chat on our website, or by emailing support@resolveai.pk. \
Our AI assistant handles routine queries instantly, with seamless escalation \
to a human specialist when needed.

ResolveAI is committed to making {topic_lower} as transparent and fair as \
possible. We publish average resolution times and customer satisfaction scores \
monthly on our website. Your feedback after each interaction helps us improve \
continuously.
"""

# Each spec: title, area, source_type, detail (~200 chars, 2-3 sentences)
_ARTICLE_SPECS: list[dict] = [
    # ── Orders (30) ───────────────────────────────────────────────────────────
    {"title": "Order Tracking via SMS and App",
     "area": "orders", "source_type": "article",
     "detail": "ResolveAI sends real-time tracking SMS at every stage from dispatch to delivery. "
               "The tracking number in your confirmation email also works on TCS, Leopard, and M&P "
               "portals. App users see a live map view for same-day deliveries."},
    {"title": "Same-Day Delivery Service",
     "area": "orders", "source_type": "article",
     "detail": "Same-day delivery is available in Karachi, Lahore, and Islamabad for orders placed "
               "before 12 PM PKT. A PKR 200 surcharge applies. Coverage zones include DHA, Gulshan, "
               "Clifton, Model Town, F-sector, and G-sector areas."},
    {"title": "Express Delivery Options",
     "area": "orders", "source_type": "article",
     "detail": "Express delivery (next business day) is available nationwide. Orders placed before "
               "3 PM PKT qualify for next-day dispatch. Express surcharge is PKR 100-300 depending "
               "on weight and destination city."},
    {"title": "Delivery to Remote and Rural Areas",
     "area": "orders", "source_type": "article",
     "detail": "ResolveAI delivers to all 36 districts of Pakistan including remote FATA and Gilgit-"
               "Baltistan regions. Delivery to remote areas takes 7-10 business days via M&P Logistics. "
               "COD is not available in select remote zones."},
    {"title": "Order Cancellation Before Dispatch",
     "area": "orders", "source_type": "article",
     "detail": "Cancellations are instant if the order is still in Processing status. After dispatch, "
               "cancellation requires refusing the delivery or initiating a return. No cancellation fee "
               "applies for pre-dispatch cancellations."},
    {"title": "Handling Damaged Packages",
     "area": "orders", "source_type": "article",
     "detail": "Photograph outer packaging damage before opening. If contents are damaged, photograph "
               "those too and report within 48 hours via the app. ResolveAI covers all courier-caused "
               "damage under its shipment insurance policy."},
    {"title": "Missing Items in Delivered Orders",
     "area": "orders", "source_type": "article",
     "detail": "Missing items are investigated within 48 hours of reporting. Provide a photo of the "
               "packaging and received contents when reporting. Replacements are dispatched via express "
               "delivery at no charge once the investigation confirms the missing item."},
    {"title": "Incorrect Items Received",
     "area": "orders", "source_type": "article",
     "detail": "Receiving an incorrect item triggers an automatic replacement dispatch. You keep the "
               "incorrect item — no return required for items below PKR 1,000. For higher-value items "
               "a pickup is scheduled simultaneously with the replacement delivery."},
    {"title": "Changing Delivery Address Post-Order",
     "area": "orders", "source_type": "article",
     "detail": "Address changes are accepted while the order is in Processing status. Changes to a "
               "different city may incur additional shipping charges. Contact support immediately after "
               "placing the order if you need to change the address."},
    {"title": "Bulk and Wholesale Order Handling",
     "area": "orders", "source_type": "article",
     "detail": "Bulk orders of 10+ units are routed through our B2B portal. Volume discounts of 5-20% "
               "apply. Bulk orders require a dedicated account manager for coordination. Delivery is "
               "arranged in agreed batches for very large orders."},
    {"title": "Pre-Order and Back-Order Policy",
     "area": "orders", "source_type": "article",
     "detail": "Pre-orders lock stock before release and are charged at time of order. Back-orders "
               "are charged only on dispatch. Both can be cancelled for a full refund before dispatch. "
               "Estimated dispatch dates are shown on the product page."},
    {"title": "Cash on Delivery Guidelines",
     "area": "orders", "source_type": "article",
     "detail": "COD is available nationwide except select remote zones. Payment must be exact as "
               "couriers may not carry change. A PKR 100 COD fee applies to orders below PKR 2,000. "
               "COD orders are prioritised after prepaid orders in dispatch queues."},
    {"title": "Order Modification After Placement",
     "area": "orders", "source_type": "article",
     "detail": "You can add or remove items, change variants, or switch delivery speed while the order "
               "is in Processing status. Modifications are not possible post-dispatch. Additional "
               "payment for added items is charged to the original payment method."},
    {"title": "International Shipping Guide",
     "area": "orders", "source_type": "article",
     "detail": "International shipping is handled via DHL to UAE, UK, USA, Canada, and Saudi Arabia. "
               "Delivery takes 7-14 business days. Customs duties are borne by the recipient. "
               "Minimum order value for international shipping is PKR 5,000."},
    {"title": "Delivery Attempt Management",
     "area": "orders", "source_type": "article",
     "detail": "Couriers make up to 3 delivery attempts. After each failed attempt you receive an SMS "
               "with rescheduling options. After 3 failed attempts, the order returns to warehouse. "
               "COD orders incur a return shipping fee after failed delivery attempts."},
    {"title": "Courier Partner Overview",
     "area": "orders", "source_type": "article",
     "detail": "ResolveAI partners with TCS, Leopard Courier, M&P Logistics, and Postex for domestic "
               "delivery. Each partner specialises in specific regions and delivery speeds. You can "
               "contact the assigned courier directly using the tracking number in your confirmation."},
    {"title": "Pickup from Courier Branch",
     "area": "orders", "source_type": "article",
     "detail": "If you prefer to collect your order, select Courier Pickup at checkout and choose the "
               "nearest branch. The order is held for 3 business days at the branch. CNIC is required "
               "for collection. Branch addresses are listed in the app."},
    {"title": "Pharmacy and Medicine Order Delivery",
     "area": "orders", "source_type": "article",
     "detail": "Medicine orders require a valid prescription upload for prescription drugs. Same-day "
               "delivery is available 24/7 for urgent medicines in major cities. Cold-chain medicines "
               "are delivered in insulated packaging with temperature monitoring."},
    {"title": "Grocery and Fresh Food Delivery",
     "area": "orders", "source_type": "article",
     "detail": "Grocery and fresh food orders are delivered within 2-4 hours of order placement in "
               "covered areas. Temperature-controlled packaging ensures freshness. Report any quality "
               "issue within 2 hours of delivery for an immediate replacement."},
    {"title": "Gift Wrapping and Special Packaging",
     "area": "orders", "source_type": "article",
     "detail": "Gift wrapping is available for PKR 150 per item. Add a personalised message (up to 150 "
               "characters) that gets printed on a gift card. Gift-wrapped orders are delivered in "
               "branded boxes with tamper-evident seals."},
    {"title": "Subscription Order Management",
     "area": "orders", "source_type": "article",
     "detail": "Subscription orders provide 10% savings on recurring purchases. Set frequency "
               "(weekly, fortnightly, monthly) and receive reminders 3 days before each dispatch. "
               "Pause or cancel anytime from Account > Subscriptions without penalty."},
    {"title": "Multi-Seller Order Splitting",
     "area": "orders", "source_type": "article",
     "detail": "Orders containing items from multiple sellers are split into separate shipments. "
               "Each shipment has its own tracking number. The checkout clearly shows which items "
               "ship together. You receive separate confirmation emails for each shipment."},
    {"title": "Order Receipt and E-Invoice",
     "area": "orders", "source_type": "article",
     "detail": "Tax invoices are emailed automatically after each successful order. Download or "
               "reprint invoices from Account > Order History anytime. Business accounts can "
               "request consolidated monthly invoices for accounting purposes."},
    {"title": "Handling Delivery Delays",
     "area": "orders", "source_type": "article",
     "detail": "If your order is delayed beyond the promised timeline, contact support to initiate "
               "a courier escalation. If the delay exceeds 5 additional business days, you are "
               "entitled to a full refund or a PKR 200 voucher as compensation."},
    {"title": "Delivery During Eid and Holidays",
     "area": "orders", "source_type": "article",
     "detail": "During Eid-ul-Fitr and Eid-ul-Adha, delivery timelines extend by 2-4 business days. "
               "Express delivery is suspended during Eid. Place orders at least 5 days before Eid "
               "to ensure delivery before the holiday break."},
    {"title": "B2B and Corporate Order Processing",
     "area": "orders", "source_type": "article",
     "detail": "Corporate accounts receive dedicated purchase order management, credit terms up to "
               "30 days, and a dedicated account manager. Minimum corporate order value is PKR 50,000 "
               "per month. Custom delivery schedules are available for regular corporate clients."},
    {"title": "Return Shipment and Reverse Logistics",
     "area": "orders", "source_type": "article",
     "detail": "Return pickups are scheduled within 24-48 hours of return approval. Our reverse "
               "logistics partners collect from your registered address. You receive a confirmation "
               "SMS when the return shipment is picked up and again when received at our warehouse."},
    {"title": "Large and Oversized Item Delivery",
     "area": "orders", "source_type": "article",
     "detail": "Items above 30 kg or exceeding standard dimensions (120x60x60 cm) are classified as "
               "oversized. Oversized items require a dedicated delivery slot booked in advance. "
               "In-home delivery and installation services are available for an additional fee."},
    {"title": "Delivery Insurance and Liability",
     "area": "orders", "source_type": "article",
     "detail": "All shipments are insured up to the declared value. For items above PKR 100,000, "
               "additional insurance documentation is prepared. In case of loss or damage, the "
               "insurance claim is processed within 5 business days of the investigation."},
    {"title": "Order Privacy and Discreet Packaging",
     "area": "orders", "source_type": "article",
     "detail": "Select Discreet Packaging at checkout for plain outer packaging with no brand "
               "markings or product description visible. The return address on discreet packages "
               "shows only our Karachi warehouse address. No product details appear on the waybill."},

    # ── Refunds (25) ──────────────────────────────────────────────────────────
    {"title": "Refund Initiation Step-by-Step",
     "area": "refunds", "source_type": "article",
     "detail": "Go to My Orders, select the item, click Return or Refund, choose the reason, upload "
               "photos if required, and submit. Our team reviews requests within 24 business hours. "
               "Approved refunds are processed automatically without further action from you."},
    {"title": "Refund Timeline by Payment Method",
     "area": "refunds", "source_type": "article",
     "detail": "EasyPaisa and JazzCash refunds arrive in 2-3 business days. Credit/debit card refunds "
               "take 5-7 business days. Bank transfer refunds take 7-10 business days. The clock "
               "starts from our processing date, not your submission date."},
    {"title": "Return Pickup Scheduling",
     "area": "refunds", "source_type": "article",
     "detail": "Schedule return pickups from My Returns in your account. Available slots are "
               "morning (9-12), afternoon (12-4), and evening (4-7). The courier calls 30 minutes "
               "before arrival. Missed pickups can be rescheduled up to 3 times before cancellation."},
    {"title": "Exchange vs Refund: Which to Choose",
     "area": "refunds", "source_type": "article",
     "detail": "Choose exchange when you want a different size, colour, or variant of the same product. "
               "Choose refund when you no longer want the product. Exchanges are processed faster "
               "(2-3 business days) compared to refunds (5-7 business days for card payments)."},
    {"title": "Defective Product Refund Policy",
     "area": "refunds", "source_type": "article",
     "detail": "Defective products qualify for a full refund regardless of when the defect is "
               "discovered within the product's warranty period. Upload a video demonstrating the "
               "defect for faster processing. Manufacturing defects are covered indefinitely."},
    {"title": "COD Order Refund to Wallet",
     "area": "refunds", "source_type": "article",
     "detail": "COD refunds are deposited to your EasyPaisa or JazzCash wallet or your bank account. "
               "Add your refund account in Account > Payment Settings before submitting the return. "
               "Refund account changes require a 24-hour security hold."},
    {"title": "Digital Product and Subscription Refunds",
     "area": "refunds", "source_type": "article",
     "detail": "Software licenses refundable within 24 hours if not activated. Subscriptions refunded "
               "within 3 days of signup for a full refund. Post-3-day subscription cancellations take "
               "effect at end of billing period with no partial refund."},
    {"title": "Partial Refund Calculation",
     "area": "refunds", "source_type": "article",
     "detail": "Partial refunds apply when you return items from a bundle deal or discount order. "
               "The refund is calculated on the actual paid price per item, not the listed price. "
               "Your refund summary is shown before you confirm the return request."},
    {"title": "Refund Status Tracking",
     "area": "refunds", "source_type": "article",
     "detail": "Track all refunds in Account > My Refunds. Status stages include: Submitted, Under "
               "Review, Approved, Pickup Scheduled, Item Received, and Refund Processed. SMS and "
               "email notifications are sent at every stage change."},
    {"title": "Warranty Claim and Manufacturer Return",
     "area": "refunds", "source_type": "article",
     "detail": "Warranty claims are processed through our platform. We coordinate with the brand's "
               "authorised service centre on your behalf. You receive a free loan unit for repairs "
               "exceeding 7 days. Repair TAT is typically 7-14 business days."},
    {"title": "Refund Dispute and Escalation",
     "area": "refunds", "source_type": "article",
     "detail": "Dispute a refund decision by contacting support within 10 days of the decision. "
               "Provide additional evidence such as photos, bank statements, or courier receipts. "
               "Disputes are reviewed by a senior team within 3 business days."},
    {"title": "Bundle and Combo Return Policy",
     "area": "refunds", "source_type": "article",
     "detail": "Returning one item from a bundle voids the bundle discount. The net refund is the "
               "original payment minus the standard price of kept items. Our support team will "
               "calculate and communicate the exact refund amount before processing."},
    {"title": "Flash Sale and Promotional Returns",
     "area": "refunds", "source_type": "article",
     "detail": "Flash sale items have a 14-day return window vs the standard 30 days. Promo vouchers "
               "used on returned orders are reinstated to your account if the order is cancelled "
               "within the promotional validity period."},
    {"title": "International Order Return",
     "area": "refunds", "source_type": "article",
     "detail": "International returns are shipped via DHL at the customer's expense unless the item "
               "is defective. Refund processing starts after we receive the item at our Karachi "
               "warehouse. International refunds take 10-15 business days due to customs clearance."},
    {"title": "Expired and Contaminated Product Refund",
     "area": "refunds", "source_type": "article",
     "detail": "Expired or contaminated products qualify for an immediate full refund plus a PKR 500 "
               "goodwill credit. Photograph the expiry date and report within 24 hours of delivery. "
               "No return pickup is required for health-safety returns."},
    {"title": "Refund for Pricing Errors",
     "area": "refunds", "source_type": "article",
     "detail": "If a product was listed at the wrong price, you may receive a corrected invoice or "
               "a cancellation with full refund. ResolveAI honours pricing errors up to 20% below "
               "the correct price. Errors greater than 20% are cancelled with apology vouchers."},
    {"title": "Gift Return and Refund to Gifter",
     "area": "refunds", "source_type": "article",
     "detail": "Gift recipients can return items without revealing the purchase price. Refunds for "
               "gifts go to the original purchaser's payment method or as store credit to the "
               "recipient's account, as selected at the time of return initiation."},
    {"title": "Overcharge and Billing Error Refund",
     "area": "refunds", "source_type": "article",
     "detail": "Billing errors are investigated within 24 hours. Confirmed overcharges are refunded "
               "within 2 business days. Provide bank statements as supporting evidence for faster "
               "resolution. Duplicate charges are auto-detected and refunded proactively."},
    {"title": "Subscription Cancellation and Pro-Rata Refund",
     "area": "refunds", "source_type": "article",
     "detail": "Annual subscriptions cancelled mid-term receive a pro-rata refund for unused months "
               "minus a 10% administrative fee. Monthly subscriptions end at the billing cycle "
               "and are not eligible for mid-cycle refunds."},
    {"title": "Refund for Delivery Failure",
     "area": "refunds", "source_type": "article",
     "detail": "If three delivery attempts fail and the order returns to warehouse, you may choose "
               "re-delivery or a full refund. Re-delivery is free within 30 days. Prepaid orders "
               "that are lost in transit receive a full refund within 5 business days."},
    {"title": "Customs and Duty Refund",
     "area": "refunds", "source_type": "article",
     "detail": "Customs duties paid on returned international orders are refundable subject to "
               "Pakistani customs regulations. The process takes 30-60 days. We submit customs "
               "refund applications on your behalf with no additional charge."},
    {"title": "Chargeback and Bank Dispute",
     "area": "refunds", "source_type": "article",
     "detail": "Contact us before initiating a bank chargeback — we resolve most issues faster "
               "through our direct process. Chargebacks lock the account temporarily during "
               "investigation. Confirmed fraudulent chargebacks result in permanent account closure."},
    {"title": "Store Credit vs Cash Refund",
     "area": "refunds", "source_type": "article",
     "detail": "Choose store credit for an instant refund with a 10% bonus. Choose cash refund "
               "for the full amount back to your payment method within the standard timeline. "
               "Store credits expire after 12 months if unused."},
    {"title": "Return Condition Assessment",
     "area": "refunds", "source_type": "article",
     "detail": "Our quality team inspects returned items and classifies them as: Excellent, Good, "
               "Fair, or Damaged. Excellent and Good items receive full refunds. Fair condition may "
               "result in a partial refund. Damaged beyond normal use receives no refund."},
    {"title": "After-Sale Service Refund",
     "area": "refunds", "source_type": "article",
     "detail": "After-sale installation or setup services are refundable if the service was not "
               "performed or was performed incorrectly. Partial refunds apply if partial service "
               "was delivered. Log a complaint within 7 days of the service date."},

    # ── Account (20) ──────────────────────────────────────────────────────────
    {"title": "Account Creation and Phone Verification",
     "area": "account", "source_type": "article",
     "detail": "Registration requires a valid Pakistani mobile number for OTP verification. OTPs "
               "expire after 10 minutes. If the OTP does not arrive, check network and retry or "
               "use email OTP as an alternative. Accounts are activated instantly upon verification."},
    {"title": "KYC Document Submission Guide",
     "area": "account", "source_type": "article",
     "detail": "Submit CNIC (both sides) or NICOP for foreign nationals. Photos must be in JPG or "
               "PNG format, minimum 1MB, taken in good lighting. Expired or blurry documents are "
               "rejected within 2 hours with a reason and resubmission instructions."},
    {"title": "KYC Rejection Causes and Resolution",
     "area": "account", "source_type": "article",
     "detail": "Common KYC rejection reasons: blurry image, expired CNIC, name mismatch with account, "
               "obstructed corners, or poor lighting. Resubmit corrected documents from Account > "
               "Verification. Each resubmission is reviewed within 4 business hours."},
    {"title": "Password Reset and Account Recovery",
     "area": "account", "source_type": "article",
     "detail": "Reset your password via SMS OTP or email link. OTP expires in 10 minutes; reset link "
               "in 30 minutes. If both are inaccessible, call our support hotline with your CNIC "
               "for manual identity verification and account recovery."},
    {"title": "Two-Factor Authentication Setup",
     "area": "account", "source_type": "article",
     "detail": "Enable 2FA in Account > Security. Supports Google Authenticator, Microsoft Authenticator, "
               "and SMS OTP. Save backup codes displayed during setup. Losing both 2FA device and "
               "backup codes requires manual identity verification for reset."},
    {"title": "Account Tier Benefits Explained",
     "area": "account", "source_type": "article",
     "detail": "Free tier: 30-day returns, standard delivery, basic support. Standard (PKR 499/month): "
               "60-day returns, express discounts, 4hr support response. Premium (PKR 999/month): "
               "90-day returns, same-day delivery, 24/7 dedicated manager, 1-hour response."},
    {"title": "Upgrading Your Account Tier",
     "area": "account", "source_type": "article",
     "detail": "Upgrade instantly in Account > Subscription. Benefits apply immediately after payment. "
               "Annual plans offer 2 months free compared to monthly billing. Payment is charged to "
               "your default payment method; change it in Account > Payment Settings first."},
    {"title": "Business Account Registration",
     "area": "account", "source_type": "article",
     "detail": "Business accounts require company registration certificate, NTN number, and "
               "authorised signatory CNIC. Registration is reviewed within 2-3 business days. "
               "Benefits include credit terms, bulk discounts, dedicated manager, and consolidated billing."},
    {"title": "Account Freeze: Causes and Resolution",
     "area": "account", "source_type": "article",
     "detail": "Accounts may be frozen due to: suspicious login activity, expired KYC, unresolved "
               "payment dispute, or policy violation. You receive an SMS with the reason. Most freezes "
               "resolve within 24-48 hours after providing requested documentation."},
    {"title": "Requesting Account Deletion",
     "area": "account", "source_type": "article",
     "detail": "Deletion requests are processed within 30 days. Active orders must be completed first. "
               "Data is anonymised within 30 days and permanently deleted after 90 days per our data "
               "retention policy. Deletion cannot be reversed after the 30-day reactivation window."},
    {"title": "Managing Multiple Delivery Addresses",
     "area": "account", "source_type": "article",
     "detail": "Save up to 10 addresses labelled Home, Office, or custom names. Set a default address "
               "for faster checkout. Include delivery instructions (e.g., floor number, gate code) "
               "in the notes field. Addresses are verified against courier serviceability automatically."},
    {"title": "Loyalty Program and ResolvePoints",
     "area": "account", "source_type": "article",
     "detail": "Earn 1 ResolvePoint per PKR 100 spent. 100 points = PKR 10 discount. Points expire "
               "after 12 months of inactivity. Double points on birthdays and during anniversary "
               "sales. Redeem at checkout or convert to charity donations."},
    {"title": "Referral Program Guide",
     "area": "account", "source_type": "article",
     "detail": "Share your referral code (found in Account > Referrals). Both you and your referral "
               "receive PKR 200 credit when they place their first order above PKR 500. No limit on "
               "referrals. Credits expire after 6 months and cannot be cashed out."},
    {"title": "Notification and Communication Preferences",
     "area": "account", "source_type": "article",
     "detail": "Customise notification channels (SMS, email, app push) and categories (orders, promotions, "
               "account security) in Account > Preferences. Security alerts (login, password change) "
               "cannot be disabled and are always sent to all active contact methods."},
    {"title": "Privacy and Data Access Settings",
     "area": "account", "source_type": "article",
     "detail": "Download all your personal data from Account > Privacy > Export My Data. The export "
               "includes order history, addresses, payment methods (masked), and communication logs. "
               "Processing takes up to 48 hours; the file link is emailed to you."},
    {"title": "Social Login and Linked Accounts",
     "area": "account", "source_type": "article",
     "detail": "Link Google or Facebook for faster login in Account > Security > Linked Accounts. "
               "Social login does not replace your password — both methods remain active. Unlink at "
               "any time. Social login is not available in regions with restricted API access."},
    {"title": "Profile Update and Name Change",
     "area": "account", "source_type": "article",
     "detail": "Update your name, email, or profile photo in Account > Profile. Name changes require "
               "resubmission of CNIC for KYC-verified accounts. Email changes trigger a confirmation "
               "link to both old and new addresses for security."},
    {"title": "Account Activity and Session Management",
     "area": "account", "source_type": "article",
     "detail": "View all active sessions in Account > Security > Active Devices. Revoke any session "
               "remotely with one click. Enable login notifications to receive an alert every time "
               "your account is accessed from a new device or location."},
    {"title": "Corporate Team Sub-Accounts",
     "area": "account", "source_type": "article",
     "detail": "Corporate accounts can create up to 20 employee sub-accounts with configurable "
               "purchase limits and category restrictions. Sub-account purchases are reported in "
               "the corporate dashboard. Centralized billing combines all sub-account transactions."},
    {"title": "Accessibility Features",
     "area": "account", "source_type": "article",
     "detail": "ResolveAI supports screen readers, high-contrast mode, and font scaling for "
               "visually impaired users. Voice navigation is available on our mobile app. "
               "Request accessible PDF invoices or large-print receipts from support."},

    # ── Payments (15) ─────────────────────────────────────────────────────────
    {"title": "EasyPaisa Payment Complete Guide",
     "area": "payments", "source_type": "article",
     "detail": "Pay via EasyPaisa by selecting it at checkout and entering your registered mobile "
               "number. Approve the payment prompt in your EasyPaisa app within 5 minutes. "
               "Refunds return to your EasyPaisa wallet within 2-3 business days."},
    {"title": "JazzCash Payment Complete Guide",
     "area": "payments", "source_type": "article",
     "detail": "JazzCash payments work on all JazzCash-registered numbers including Jazz, Warid, and "
               "Zong. Select JazzCash at checkout, enter your number, and confirm the USSD push "
               "notification. The payment is confirmed within 30 seconds."},
    {"title": "Credit and Debit Card Payment Guide",
     "area": "payments", "source_type": "article",
     "detail": "Visa, Mastercard, and UnionPay cards are accepted. 3D Secure authentication is "
               "required for first-time card use. Card details are tokenised and never stored on "
               "our servers. Contact your bank to enable international and e-commerce transactions."},
    {"title": "Bank Transfer (IBFT) Payment Guide",
     "area": "payments", "source_type": "article",
     "detail": "Available for orders above PKR 5,000. Transfer within 24 hours using the account "
               "details provided at checkout. Include your order number as the transfer reference. "
               "Confirmation takes 1-2 hours after transfer. Orders are cancelled after 24 hours."},
    {"title": "Raast Instant Payment Guide",
     "area": "payments", "source_type": "article",
     "detail": "Raast is SBP's national instant payment system, free and available 24/7. Select "
               "Raast at checkout, enter your Raast ID (IBAN or phone-linked ID), and confirm. "
               "Supported by all major Pakistani banks. Transactions settle in under 30 seconds."},
    {"title": "Resolving Payment Failures",
     "area": "payments", "source_type": "article",
     "detail": "Common causes: insufficient balance, expired card, bank security block, or session "
               "timeout. Check your bank app for the decline reason. If charged without order "
               "confirmation, do not retry — contact support with your transaction reference."},
    {"title": "Duplicate Charge Investigation",
     "area": "payments", "source_type": "article",
     "detail": "Duplicate charges from network timeouts are auto-detected and reversed within 3 "
               "business days. If not reversed, submit a support ticket with screenshots of both "
               "charges. Our payments team coordinates directly with your bank or wallet provider."},
    {"title": "Installment Plans and BNPL",
     "area": "payments", "source_type": "article",
     "detail": "Installment plans of 3, 6, and 12 months at 0% markup are available via Meezan Bank "
               "and Faysal Bank for eligible cardholders. Buy Now Pay Later via PostEx Payments "
               "works without a credit card for orders above PKR 3,000."},
    {"title": "Pre-Authorization and Payment Holds",
     "area": "payments", "source_type": "article",
     "detail": "At checkout, funds are authorised (not captured). Capture occurs at dispatch. "
               "Pre-authorisations lapse within 5-7 days if not captured. If an item goes out of "
               "stock, the pre-auth is released within 3-5 business days."},
    {"title": "Payment Security and Fraud Prevention",
     "area": "payments", "source_type": "article",
     "detail": "All transactions pass through a real-time fraud detection engine. Suspicious "
               "transactions are placed on manual review (under 2 hours). Never share OTPs, PINs, "
               "or CVV with anyone claiming to be from ResolveAI — we never ask."},
    {"title": "Transaction History and E-Receipts",
     "area": "payments", "source_type": "article",
     "detail": "Download transaction history and e-receipts from Account > Transaction History. "
               "Filter by date range, payment method, or order type. Tax invoices are emailed "
               "automatically and also available in Account > Order History."},
    {"title": "Cash on Delivery Payment Guide",
     "area": "payments", "source_type": "article",
     "detail": "Pay the exact amount to the courier in PKR cash or via POS machine (available with "
               "select courier partners). A PKR 100 COD fee applies to orders under PKR 2,000. "
               "COD is not available for digital products, heavy appliances, or remote zones."},
    {"title": "Promotional Credits and Vouchers",
     "area": "payments", "source_type": "article",
     "detail": "Apply voucher codes at checkout in the Promo Code field. One code per order. "
               "Vouchers have expiry dates and minimum order requirements. Unused promotional "
               "credits from cancelled orders are reinstated automatically within 24 hours."},
    {"title": "Currency and Pricing Policy",
     "area": "payments", "source_type": "article",
     "detail": "All prices are in Pakistani Rupees (PKR). International card holders are charged "
               "in PKR and converted by their bank. Dynamic pricing occurs for high-demand items "
               "during flash sales but is never changed after order confirmation."},
    {"title": "Payment Method Switching After Order",
     "area": "payments", "source_type": "article",
     "detail": "Payment method changes are possible while the order is in Processing status and "
               "payment has not been captured. Contact support to void the current authorisation "
               "and receive a new payment link. Method switches are processed within 2 hours."},

    # ── Policy (20 article-type + 30 policy-type) ─────────────────────────────
    {"title": "Customer Data Privacy Practices",
     "area": "policy", "source_type": "policy",
     "detail": "We collect only data necessary to provide our services. Data is never sold to "
               "third parties. You can review and export your data at any time from Account settings. "
               "All data processing complies with Pakistan's PECA 2016 and Prevention of Electronic "
               "Crimes Act regulations."},
    {"title": "Terms of Service Key Points",
     "area": "policy", "source_type": "policy",
     "detail": "Users must be 18+ or have parental consent. Accounts are non-transferable. "
               "Prohibited activities include fraud, harassment, and misuse of refunds. "
               "ResolveAI reserves the right to suspend accounts that violate these terms immediately."},
    {"title": "Domestic Shipping Policy Details",
     "area": "policy", "source_type": "policy",
     "detail": "Free shipping on orders above PKR 2,500. Shipping charges are calculated by weight "
               "and distance. Three delivery attempts are made before return to warehouse. Delivery "
               "addresses must include complete house/office details for successful delivery."},
    {"title": "Anti-Fraud and Security Practices",
     "area": "policy", "source_type": "policy",
     "detail": "All transactions are screened by our fraud detection AI. High-risk transactions "
               "require additional verification. ResolveAI will never ask for passwords, complete "
               "card numbers, or OTPs via any channel. Report suspicious requests immediately."},
    {"title": "Complaints and Escalation Framework",
     "area": "policy", "source_type": "policy",
     "detail": "Level 1 support resolves 90% of issues within 4 hours. Level 2 escalations are "
               "handled by team leads within 1-2 business days. Level 3 formal complaints get a "
               "written response from Operations within 5 business days."},
    {"title": "Cookie and Tracking Policy",
     "area": "policy", "source_type": "policy",
     "detail": "We use analytics, functional, and marketing cookies. Essential cookies cannot be "
               "disabled. Manage preferences via the cookie settings panel. Marketing cookies can "
               "be disabled without affecting core functionality."},
    {"title": "Data Retention and Deletion Schedule",
     "area": "policy", "source_type": "policy",
     "detail": "Transaction data is retained for 7 years per tax regulations. Account data is "
               "deleted 90 days after account closure. Backup purge occurs at 180 days. Legal "
               "holds may extend retention when required by courts or regulators."},
    {"title": "Acceptable Use Policy",
     "area": "policy", "source_type": "policy",
     "detail": "Platform may not be used for illegal transactions, money laundering, reselling "
               "restricted goods, or abusing promotional offers. Automated bots require API "
               "partnership approval. Bulk account creation for fraud is permanently banned."},
    {"title": "Intellectual Property Rights",
     "area": "policy", "source_type": "policy",
     "detail": "All platform content including product descriptions, images, and software is "
               "protected by copyright. Reproduction without written permission is prohibited. "
               "Seller-listed content remains the property of the respective seller."},
    {"title": "Third-Party Seller Policy",
     "area": "policy", "source_type": "policy",
     "detail": "Third-party sellers are responsible for product quality and accurate descriptions. "
               "ResolveAI mediates disputes between buyers and sellers. Verified seller badges "
               "indicate sellers who have passed our quality assessment programme."},
    {"title": "Accessibility Policy",
     "area": "policy", "source_type": "policy",
     "detail": "ResolveAI is committed to WCAG 2.1 AA compliance. Screen reader support, "
               "keyboard navigation, and colour contrast compliance are maintained across all "
               "platforms. Report accessibility issues to accessibility@resolveai.pk."},
    {"title": "Environmental and Sustainability Policy",
     "area": "policy", "source_type": "policy",
     "detail": "We use recyclable packaging for 80% of shipments. Carbon emissions are offset "
               "through partnerships with local reforestation projects. Our target is carbon "
               "neutrality by 2027. Customers can opt for eco-packaging at checkout."},
    {"title": "Child Safety and Age Verification",
     "area": "policy", "source_type": "policy",
     "detail": "Age-restricted products require CNIC verification confirming 18+ status. "
               "Children under 13 are prohibited from creating accounts. Parental accounts "
               "can set spending limits and product category restrictions for family members."},
    {"title": "Dispute Resolution and Arbitration",
     "area": "policy", "source_type": "policy",
     "detail": "Disputes are first addressed through our internal escalation process. Unresolved "
               "disputes go to binding arbitration under Pakistan Arbitration Act. Arbitration "
               "hearings are conducted in Karachi. Court proceedings are a last resort."},
    {"title": "Price Match Guarantee Policy",
     "area": "policy", "source_type": "policy",
     "detail": "We match verified lower prices from authorised dealers within 24 hours of purchase. "
               "Submit a price match request with a screenshot of the competitor's listing. "
               "Applies to identical products sold by authorised dealers only, not grey market."},
    {"title": "Product Authenticity Guarantee",
     "area": "policy", "source_type": "policy",
     "detail": "All products are sourced from authorised distributors and carry manufacturer "
               "warranties. Each product page shows the brand's official warranty terms. "
               "Counterfeit products discovered post-sale receive a full refund plus compensation."},
    {"title": "Prohibited and Restricted Products",
     "area": "policy", "source_type": "policy",
     "detail": "Strictly prohibited: weapons, narcotics, counterfeit goods, adult content, "
               "and hazardous materials. Restricted categories requiring documentation: medicines "
               "(prescription), tobacco (age verification), and high-value electronics (invoice)."},
    {"title": "Seller Commission and Fee Structure",
     "area": "policy", "source_type": "policy",
     "detail": "Platform commission ranges from 5-15% based on product category. Monthly seller "
               "dashboard shows real-time sales, commissions, and payouts. Seller payouts are "
               "processed weekly on Thursdays to registered bank accounts."},
    {"title": "Force Majeure and Service Disruption",
     "area": "policy", "source_type": "policy",
     "detail": "In force majeure events (natural disasters, civil unrest, power outages), delivery "
               "timelines may be extended without compensation. ResolveAI proactively communicates "
               "disruptions and offers order holds or full refunds during prolonged outages."},
    {"title": "API and Developer Access Policy",
     "area": "policy", "source_type": "policy",
     "detail": "API access requires a developer account and approval. Rate limits apply: 1,000 "
               "requests per hour on standard tier. Webhooks are available for order, payment, and "
               "inventory events. API abuse results in immediate key revocation."},
    {"title": "Loyalty Program Terms and Conditions",
     "area": "policy", "source_type": "policy",
     "detail": "ResolvePoints are non-transferable and non-encashable. Maximum redemption per order "
               "is PKR 500 for Free tier and unlimited for Premium. Points earned on returned orders "
               "are automatically deducted. Abuse of the loyalty system results in account suspension."},
    {"title": "WhatsApp Business Communication Policy",
     "area": "policy", "source_type": "policy",
     "detail": "We send order updates, support responses, and promotions via WhatsApp. You can "
               "opt out of promotions by replying STOP. Support conversations are retained for "
               "90 days. We never send unsolicited promotional messages without prior consent."},
    {"title": "Influencer and Affiliate Programme Terms",
     "area": "policy", "source_type": "policy",
     "detail": "Affiliates earn 3-8% commission on referred sales. Minimum payout threshold is "
               "PKR 2,000. Commissions are credited after the return window expires. Fraudulent "
               "referrals result in commission clawback and affiliate programme termination."},
    {"title": "Health and Medical Product Policy",
     "area": "policy", "source_type": "policy",
     "detail": "All pharmaceutical products are sourced from DRAP-licensed distributors. Prescription "
               "medicines require a valid prescription verified by our pharmacy team. Self-medication "
               "guidance is available from our registered pharmacists via chat."},
    {"title": "Financial Regulation Compliance",
     "area": "policy", "source_type": "policy",
     "detail": "ResolveAI complies with SBP Payment Systems Regulations, AML/CFT requirements, "
               "and SECP guidelines for fintech services. KYC is mandatory for all financial "
               "transactions above PKR 25,000. Suspicious transactions are reported to FMU."},
    {"title": "Subscription Auto-Renewal Terms",
     "area": "policy", "source_type": "policy",
     "detail": "Subscriptions auto-renew unless cancelled 24 hours before the renewal date. "
               "You receive a reminder 7 days before each renewal. Failed renewal payments trigger "
               "a 5-day grace period before downgrade to Free tier. Reinstate anytime from settings."},
    {"title": "Product Review and Ratings Policy",
     "area": "policy", "source_type": "policy",
     "detail": "Only verified purchasers may review products. Reviews must be honest and relevant. "
               "Sponsored reviews must be disclosed. Defamatory, abusive, or competitor-seeded "
               "reviews are removed. Businesses may respond to reviews via seller dashboard."},
    {"title": "Lost and Found Package Policy",
     "area": "policy", "source_type": "policy",
     "detail": "Lost packages are investigated within 5 business days via GPS data and courier logs. "
               "Confirmed losses are refunded in full plus a PKR 300 goodwill credit. Packages "
               "found after refund are recalled at our expense or you may keep them guilt-free."},
    {"title": "Payment Dispute Resolution Process",
     "area": "policy", "source_type": "policy",
     "detail": "Payment disputes are resolved within 5-10 business days. We coordinate with banks "
               "and payment providers directly on your behalf. All dispute communications are "
               "documented and a resolution letter is issued after investigation."},
    {"title": "Seasonal and Promotional Campaign Rules",
     "area": "policy", "source_type": "policy",
     "detail": "Flash sale prices are valid only for the sale duration and displayed quantity. "
               "Orders placed during sales are processed at sale prices even if shipped post-sale. "
               "Promotional stacking (multiple codes) is not permitted unless explicitly stated."},

    # ── General (10) ──────────────────────────────────────────────────────────
    {"title": "Getting Started: First Order Guide",
     "area": "general", "source_type": "article",
     "detail": "Browse products, add to cart, choose delivery address and payment method, then "
               "confirm. Guest checkout is available without account creation. Creating an account "
               "enables order tracking, returns management, and loyalty points."},
    {"title": "Using the ResolveAI Mobile App",
     "area": "general", "source_type": "article",
     "detail": "The app offers AR product preview, fingerprint/face ID login, push notifications, "
               "and offline wishlist browsing. Download from Google Play or App Store. Requires "
               "Android 8+ or iOS 13+. App-exclusive deals are available weekly."},
    {"title": "WhatsApp Customer Support Guide",
     "area": "general", "source_type": "article",
     "detail": "Message our WhatsApp number for instant AI assistance 24/7. Type your issue in "
               "plain English or Urdu. For account-specific queries, the AI will verify your "
               "identity before sharing order details. Human escalation is available anytime."},
    {"title": "Live Chat Support Guide",
     "area": "general", "source_type": "article",
     "detail": "Access live chat via the chat bubble on website or app. AI handles common queries "
               "instantly. Human agent queue during peak hours is under 3 minutes. Chat history "
               "is saved to your account for follow-up reference."},
    {"title": "Seasonal Sale Shopping Tips",
     "area": "general", "source_type": "article",
     "detail": "Add items to wishlist before the sale to track price changes. Premium members get "
               "1-hour early access to Eid and Black Friday sales. Set deal alerts for specific "
               "products in Account > Alerts. Flash deals sell out in minutes — act fast."},
    {"title": "ResolvePoints Loyalty Rewards",
     "area": "general", "source_type": "article",
     "detail": "Earn 1 point per PKR 100 spent; 100 points = PKR 10 discount. Birthday bonus: "
               "double points for 7 days around your birthday. Donate points to partner charities "
               "at 1:1 value. Points leaderboard shows your ranking among customers."},
    {"title": "Eco-Friendly Shopping Options",
     "area": "general", "source_type": "article",
     "detail": "Select Eco Packaging at checkout to receive orders in 100% recyclable materials. "
               "Digital receipts eliminate paper waste. Our Green Sellers programme highlights "
               "vendors with sustainable supply chains. 1 ResolvePoint donated per eco order."},
    {"title": "Corporate Social Responsibility",
     "area": "general", "source_type": "article",
     "detail": "1% of each transaction is donated to our education foundation. ResolveAI partners "
               "with local artisans to list handmade products. Our digital literacy programme "
               "trains 1,000 small business owners annually in e-commerce skills."},
    {"title": "Accessibility Support Services",
     "area": "general", "source_type": "article",
     "detail": "Customers with disabilities can request screen-reader-compatible order confirmations, "
               "large-print invoices, or phone-based support. Our trained accessibility support "
               "team is available Monday-Saturday 9 AM to 9 PM. Email access@resolveai.pk."},
    {"title": "Newsletter and Communication Opt-In Guide",
     "area": "general", "source_type": "article",
     "detail": "Subscribe to our weekly deals newsletter in Account > Preferences > Communications. "
               "Separate opt-ins for SMS alerts, email deals, and WhatsApp promotions. Unsubscribe "
               "links are included in every communication. Your data is never shared with advertisers."},
]


def _expand_article(spec: dict, art_id: str) -> dict:
    """Expand a compact spec into a full ~2200-char article using the template."""
    title = spec["title"]
    area = spec["area"]
    topic_lower = title.lower()
    content = _ARTICLE_TEMPLATE.format(
        title=title,
        area=area,
        topic_lower=topic_lower,
        detail=spec["detail"],
    )
    return {
        "id": art_id,
        "title": title,
        "content": content.strip(),
        "source_type": spec["source_type"],
        "product_area": area,
        "language": "en",
        "confidentiality": "public",
    }


def generate_articles() -> list[dict]:
    articles = []
    for i, spec in enumerate(_ARTICLE_SPECS, start=1):
        articles.append(_expand_article(spec, f"art_{i:04d}"))
    return articles


# ── ticket templates ──────────────────────────────────────────────────────────

_TICKET_TEMPLATES: list[dict] = [
    {"product_area": "orders", "language": "en",
     "question": "My order has been in transit for 7 days. What is happening?",
     "answer": "We sincerely apologise for the delay. We have escalated your shipment with our "
               "courier partner TCS. Your order is currently held at the Karachi hub due to high "
               "volume. It should be delivered within the next 2 business days. We are monitoring "
               "it closely and will update you immediately if anything changes."},
    {"product_area": "orders", "language": "roman_ur",
     "question": "Mera order 3 din pehle dispatch hua tha, abhi tak nahi aaya?",
     "answer": "Aap ki pareshani samajh aa rahi hai. Aap ka order TCS ke saath dispatch hua hai "
               "aur filhaal transit mein hai. Delivery estimate 2-4 business days hai. Tracking "
               "number SMS mein bhej diya gaya tha. Agar kal tak na aaye toh hum courier se "
               "escalate karein ge aur aap ko update karein ge."},
    {"product_area": "orders", "language": "en",
     "question": "I received the wrong item. I ordered a blue shirt but got a red one.",
     "answer": "We are sorry for this packing error. We will arrange an immediate replacement. "
               "Please keep the incorrect item — no return is required for items below PKR 1,000. "
               "The correct blue shirt will be dispatched within 24 hours via express delivery. "
               "You will receive a new tracking number shortly."},
    {"product_area": "orders", "language": "roman_ur",
     "question": "Main ne order cancel kiya tha lekin abhi bhi dispatch show ho raha hai?",
     "answer": "Aap ka cancellation request receive hua tha lekin unfortunately order dispatch ho "
               "chuka tha. Humne courier ko rokne ki koshish ki lekin mumkin nahi ho saka. Jab "
               "order deliver ho toh simply refuse kar dein. Refund 5-7 business days mein process "
               "ho ga. Inconvenience ke liye ek PKR 200 voucher aap ke account mein add kar diya."},
    {"product_area": "orders", "language": "en",
     "question": "Can I change my delivery address? I moved to a new location.",
     "answer": "Yes, address changes are possible if your order is still in Processing status. "
               "I can see your order is still processing. I have updated your delivery address. "
               "Please confirm the new address is correct in your order details. If the order "
               "has already dispatched, address changes are unfortunately not possible."},
    {"product_area": "orders", "language": "roman_ur",
     "question": "Mujhe parcel delivery pe ghar pe koi nahi mila, ab kya hoga?",
     "answer": "Courier ne delivery attempt kiya tha lekin koi available nahi tha. Wo kal dubara "
               "try karega. Aap chahtey hain toh delivery time slot reschedule kar saktey hain "
               "ya nearest courier office se pickup bhi possible hai. Courier office ka address "
               "aur timing alag se SMS kar dete hain."},
    {"product_area": "orders", "language": "en",
     "question": "My order shows delivered but I never received it.",
     "answer": "This is very concerning. We have immediately opened an investigation with our "
               "courier partner Leopard. They have been asked to provide GPS delivery confirmation "
               "within 24 hours. Please also check with neighbours and building reception. We will "
               "resolve this within 48 hours with re-delivery or a full refund."},
    {"product_area": "orders", "language": "roman_ur",
     "question": "Kya main order place karne ke baad item add kar sakta hun?",
     "answer": "Agar aap ka order abhi Processing status mein hai toh items add kiye ja saktey "
               "hain. Main aap ka order check kar raha hun... order abhi bhi processing mein hai. "
               "Kaunsa item add karna chahte hain? Additional amount aap ki original payment "
               "method pe charge ho ga aur revised invoice email par milega."},
    {"product_area": "orders", "language": "en",
     "question": "What is the estimated delivery time for Quetta?",
     "answer": "For Quetta, standard delivery takes 5-7 business days through M&P Logistics. "
               "Express delivery is not available for Quetta at this time. Orders are dispatched "
               "from our Karachi warehouse. You will receive tracking updates via SMS at each stage."},
    {"product_area": "orders", "language": "roman_ur",
     "question": "Mere order ka packaging damage tha, products sahi hain ya nahi?",
     "answer": "Pehle sab items check karein. Agar koi bhi item damage hai toh turant photo lein "
               "aur hum se share karein. Packaging damage ki wajah se andar ka saman safe rehta "
               "hai aksar. Lekin koi cheez damage nikle toh return/replace request instantly "
               "process ho gi. Photos ke saath report submit karein app mein."},
    {"product_area": "refunds", "language": "en",
     "question": "I returned my item 2 weeks ago but still no refund.",
     "answer": "I can see your return was received and approved. The refund was initiated to your "
               "JazzCash account. JazzCash transfers can take 3-5 business days due to bank "
               "processing. If you still have not received it, please provide your JazzCash number "
               "and we will verify the transfer status directly with them."},
    {"product_area": "refunds", "language": "roman_ur",
     "question": "Mera refund credit card pe kab aayega?",
     "answer": "Aap ka refund 3 din pehle process hua tha. Credit card refunds bank ke processing "
               "time ke mutabiq 5-7 business days mein reflect hote hain. Bank holidays aur weekends "
               "is timeline mein count nahi hote. Agar 7 business days mein nahi aaya toh bank se "
               "rabta karein aur refund reference number share karein jo email mein bheja gaya tha."},
    {"product_area": "refunds", "language": "en",
     "question": "I want to return a sale item. Is that allowed?",
     "answer": "Sale items can be returned within 14 days of delivery instead of the standard "
               "30 days. The item must be in original condition with tags. If the item is defective, "
               "the full 30-day return policy applies. Please initiate the return through your "
               "order history in the app and select the appropriate reason."},
    {"product_area": "refunds", "language": "roman_ur",
     "question": "Cash on delivery pe liya tha, refund kaise milega?",
     "answer": "COD refunds ke liye aap ka bank account ya EasyPaisa/JazzCash number chahiye. "
               "Account settings mein refund details update karein. Ek baar information provide "
               "ho jaane ke baad refund 5-7 business days mein process ho ta hai. Agar aap ka "
               "account registered nahi hai toh support se rabta karein."},
    {"product_area": "refunds", "language": "en",
     "question": "I was charged twice for the same order.",
     "answer": "I can see your transaction history and you are correct — there appear to be two "
               "charges for your order. One appears to be a pre-authorisation that should have "
               "been released. I am escalating this to our payments team now. The duplicate charge "
               "will be reversed within 2-3 business days with email confirmation."},
    {"product_area": "refunds", "language": "roman_ur",
     "question": "Mujhe partial refund mila, puri amount kyun nahi di?",
     "answer": "Partial refund is liye issue hua kyunki aap ne order discount pe buy kiya tha. "
               "Refund policy ke mutabiq discounted orders ka refund actual paid amount ke hisaab "
               "se hota hai. Aap ki order summary check karein — refund amount wahi hai jo aap ne "
               "actually pay kiya tha. Agar koi error lagta hai toh details share karein."},
    {"product_area": "account", "language": "en",
     "question": "I cannot log in to my account. It says my password is incorrect.",
     "answer": "Let me help you reset your password. Please click Forgot Password on the login "
               "page and enter your registered email or phone number. An OTP will be sent to your "
               "phone. If your phone number has changed, I can help after verifying your identity "
               "with CNIC details. Shall I walk you through the process?"},
    {"product_area": "account", "language": "roman_ur",
     "question": "Mera account freeze ho gaya hai, kyun?",
     "answer": "Account freeze kai wajuhaat se ho sakti hai jaise suspicious activity, payment "
               "dispute, ya KYC expiry. Main aap ka account check kar raha hun... laga hai aap ki "
               "CNIC verification expire ho gayi hai. Updated CNIC ki photos submit karein aur "
               "24 ghante mein account unfreeze ho jayega. Settings > Verification mein jayen."},
    {"product_area": "account", "language": "en",
     "question": "How do I enable two-factor authentication?",
     "answer": "Go to Account Settings > Security > Two-Factor Authentication. Choose SMS OTP "
               "or Authenticator App. For SMS, just toggle it on and verify with the OTP sent "
               "to your phone. For an authenticator app, scan the QR code and enter the 6-digit "
               "code to confirm. Save your backup codes in a safe place."},
    {"product_area": "account", "language": "roman_ur",
     "question": "Main ne account delete karne ki request di thi, kab hoga?",
     "answer": "Account deletion request receive ho gayi hai. Process 30 days mein complete "
               "hoti hai. Is period mein aap account reactivate kar saktey hain. Active orders "
               "aur pending refunds pehle complete hone chahiye. Deletion ke baad aap ka data "
               "90 days mein permanently delete ho jayega policy ke mutabiq."},
    {"product_area": "payments", "language": "en",
     "question": "My EasyPaisa payment failed but money was deducted.",
     "answer": "This can happen due to a network timeout during payment processing. The deducted "
               "amount will be automatically refunded to your EasyPaisa wallet within 24-72 hours. "
               "Please do not retry the payment as this may cause a duplicate charge. If not "
               "returned within 72 hours, contact us with your EasyPaisa transaction reference."},
    {"product_area": "payments", "language": "roman_ur",
     "question": "Credit card se payment nahi ho rahi, error aa raha hai.",
     "answer": "Credit card error aksar bank ki taraf se block ki wajah se aata hai. Apne bank "
               "se rabta karein aur online transactions enable karein. Dusri wajah card expiry "
               "ya galat CVV bhi ho sakti hai. Specifically kaunsa error message aa raha hai mujhe "
               "batayein toh aur bhi help kar sakta hun."},
    {"product_area": "payments", "language": "en",
     "question": "Can I pay in installments without a credit card?",
     "answer": "Yes, our Buy Now Pay Later option via PostEx Payments works without a credit card "
               "for orders above PKR 3,000. You can also use installment plans through Meezan Bank "
               "and Faysal Bank debit cards. 0% markup plans are available for 3, 6, and 12 month "
               "tenures. Select your preferred plan at checkout."},
    {"product_area": "general", "language": "en",
     "question": "What are your customer service hours?",
     "answer": "Our AI support is available 24/7 and handles most issues instantly. Human agents "
               "are available Monday to Saturday 9 AM to 10 PM PKT. On Sundays, only AI support "
               "and emergency escalations are handled. Premium tier customers have 24/7 human "
               "support access. We aim to respond within minutes during business hours."},
    {"product_area": "general", "language": "roman_ur",
     "question": "App mein naya account banana hai lekin OTP nahi aa raha.",
     "answer": "OTP delay kai wajuhaat se ho sakta hai. Pehle check karein SMS blocked toh nahi "
               "hai. Network coverage bhi wajah ho sakti hai. 2-3 minute wait karein phir Resend "
               "OTP click karein. Agar phir bhi na aaye toh Email OTP option use karein. Warna "
               "humari helpline pe call karein aur hum manually account verify kar denge."},
    {"product_area": "orders", "language": "en",
     "question": "How do I track my order using the tracking number?",
     "answer": "Your tracking number is in the dispatch confirmation SMS and email. Enter it at "
               "resolveai.pk/track or directly on the courier's website. For TCS use tcs.com.pk, "
               "for Leopard use leopardscourier.com.pk. The app also shows live tracking under "
               "My Orders. Status updates every 2-4 hours during business days."},
    {"product_area": "refunds", "language": "en",
     "question": "How do I initiate a return for a defective product?",
     "answer": "Go to My Orders, select the item, click Return/Refund, choose Defective Product "
               "as the reason, describe the defect, and upload photos or a short video. Our team "
               "reviews defect claims within 12 business hours. Approved claims get a free pickup "
               "scheduled and replacement dispatched simultaneously."},
    {"product_area": "account", "language": "en",
     "question": "I need to update my CNIC for KYC. How do I do it?",
     "answer": "Go to Account > Verification > Update CNIC. Upload clear photos of both sides "
               "of your new CNIC. Ensure the text is sharp and no corners are obscured. "
               "Verification is reviewed within 4 business hours. Your account remains active "
               "during the review period."},
    {"product_area": "payments", "language": "en",
     "question": "What is Raast and how do I use it to pay?",
     "answer": "Raast is SBP's national instant payment system. It is free and processes in "
               "under 30 seconds. Select Raast at checkout, enter your Raast ID (your IBAN or "
               "phone-linked ID registered with your bank), and confirm. Supported by HBL, "
               "Meezan, MCB, NBP, and most major banks."},
    {"product_area": "general", "language": "en",
     "question": "How do I join the ResolvePoints loyalty program?",
     "answer": "You are automatically enrolled in ResolvePoints when you create an account. "
               "Start earning immediately — 1 point per PKR 100 spent. Check your balance in "
               "Account > My Rewards. Redeem at checkout for discounts. Birthday bonus gives "
               "double points for 7 days around your registered birthday."},
]


def _make_more_tickets(base: list[dict], target: int) -> list[dict]:
    """Cycle through base templates to fill up to target count."""
    tickets: list[dict] = []
    for i, t in enumerate(base, start=1):
        tickets.append({"id": f"ticket_{i:04d}", **t})

    idx = len(tickets) + 1
    source = base * ((target // len(base)) + 2)
    while len(tickets) < target:
        t = source[idx % len(source)]
        variant = {
            "id": f"ticket_{idx:04d}",
            "product_area": t["product_area"],
            "language": t["language"],
            "question": t["question"] + f" [ref #{idx}]",
            "answer": t["answer"],
        }
        tickets.append(variant)
        idx += 1

    return tickets[:target]


def generate_tickets(count: int = 500) -> list[dict]:
    return _make_more_tickets(_TICKET_TEMPLATES, count)


# ── user profiles ─────────────────────────────────────────────────────────────

def _make_phone() -> str:
    prefix = random.choice(["300", "301", "302", "303", "311", "312", "313", "321", "333", "345"])
    digits = "".join([str(random.randint(0, 9)) for _ in range(7)])
    return f"+92{prefix}{digits}"


def _make_email(name: str) -> str:
    domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"]
    slug = name.lower().replace(" ", ".") + str(random.randint(10, 99))
    return f"{slug}@{random.choice(domains)}"


def generate_users(count: int = 30) -> list[dict]:
    users: list[dict] = []
    used_phones: set[str] = set()
    for _ in range(count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        phone = _make_phone()
        while phone in used_phones:
            phone = _make_phone()
        used_phones.add(phone)
        users.append({
            "id": str(uuid.uuid4()),
            "phone": phone,
            "email": _make_email(name),
            "full_name": name,
            "plan_tier": random.choice(["free", "standard", "premium"]),
            "account_status": random.choices(
                ["active", "frozen", "closed"], weights=[9, 1, 0]
            )[0],
            "language_pref": random.choice(["en", "ur", "roman_ur"]),
            "metadata": {
                "city": random.choice(CITIES),
                "cnic": "00000-0000000-0",
                "orders": [
                    f"ORD-2024-{random.randint(1000, 9999)}"
                    for _ in range(random.randint(0, 5))
                ],
            },
        })
    return users


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  wrote {len(records)} records -> {path}")


def generate_local() -> None:
    print("Generating synthetic data (local template mode)...")

    users = generate_users(30)
    _write_jsonl(DATA_DIR / "user_profiles.jsonl", users)

    articles = generate_articles()
    _write_jsonl(DATA_DIR / "kb_articles.jsonl", articles)

    tickets = generate_tickets(540)
    _write_jsonl(DATA_DIR / "synthetic_tickets.jsonl", tickets)

    print(f"\nDone. Generated:")
    print(f"  {len(users)} user profiles")
    print(f"  {len(articles)} KB articles / policy snippets")
    print(f"  {len(tickets)} synthetic support tickets")


def generate_with_llm() -> None:
    """Enhance existing data with LLM-generated variations (requires OPENAI_API_KEY)."""
    import asyncio

    sys.path.insert(0, str(ROOT))
    from app.config import get_settings

    settings = get_settings()
    if not settings.openai_api_key:
        print("OPENAI_API_KEY not set — falling back to local generation.")
        generate_local()
        return

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def _llm_articles(n: int = 50) -> list[dict]:
        prompt = (
            f"Generate {n} diverse customer support knowledge-base articles for a Pakistani "
            "fintech/e-commerce platform called ResolveAI. Topics: orders, refunds, account, "
            "payments, policy. Each article 600+ words. Mix English and Roman Urdu. "
            'Return JSON: {"articles": [{"title":"...","content":"...","product_area":"...","source_type":"article|policy","language":"en|roman_ur"}]}'
            " Pakistani context: EasyPaisa, JazzCash, CNIC (use fake 00000-0000000-0), Karachi, Lahore."
        )
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=4000,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return data.get("articles", [])

    async def run() -> None:
        generate_local()
        print("\nEnhancing with LLM-generated articles...")
        try:
            extra = await _llm_articles(30)
            if extra:
                existing = [
                    json.loads(line)
                    for line in (DATA_DIR / "kb_articles.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                start_id = len(existing) + 1
                for i, art in enumerate(extra):
                    art["id"] = f"art_{start_id + i:04d}"
                    art.setdefault("confidentiality", "public")
                    existing.append(art)
                _write_jsonl(DATA_DIR / "kb_articles.jsonl", existing)
                print(f"  Added {len(extra)} LLM-generated articles.")
        except Exception as exc:
            print(f"  LLM generation failed ({exc}) — using local data only.")

    asyncio.run(run())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic ResolveAI seed data")
    parser.add_argument(
        "--use-llm", action="store_true",
        help="Enhance output with OpenAI generation (requires OPENAI_API_KEY)"
    )
    args = parser.parse_args()
    if args.use_llm:
        generate_with_llm()
    else:
        generate_local()


if __name__ == "__main__":
    main()
