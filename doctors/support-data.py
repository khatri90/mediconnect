# Save this as a separate Python file or run it in Django shell to populate initial FAQs

from doctors.models import FAQ

# Delete existing FAQs if you want to start fresh
# FAQ.objects.all().delete()

# Create general FAQs
faq_data = [
    # General FAQs
    {
        'question': 'How do I reschedule an appointment?',
        'answer': 'You can reschedule an appointment through the Appointments section of your dashboard. Simply locate the appointment you wish to reschedule, click the "Reschedule" button, and select a new available time slot.',
        'category': 'appointments',
        'order': 1
    },
    {
        'question': 'How do I update my billing information?',
        'answer': 'To update your billing information, go to your user profile and select the "Billing" tab. From there, you can add, remove, or update payment methods and view your billing history.',
        'category': 'billing',
        'order': 1
    },
    {
        'question': 'Can I download my medical records?',
        'answer': 'Yes, you can download your medical records from the Health Records section of your dashboard. Select the records you want to download and click the "Export" button. Files are available in PDF format.',
        'category': 'general',
        'order': 1
    },
    {
        'question': 'How do I share my health data with my doctor?',
        'answer': 'You can share your health data with your doctor by going to your profile and selecting "Share Profile." Enter your doctor\'s email address or select them from your contacts list, then choose which data you want to share and for how long.',
        'category': 'general',
        'order': 2
    },
    {
        'question': 'What should I do if I encounter a technical issue?',
        'answer': 'If you encounter a technical issue, first try refreshing the page or logging out and back in. If the problem persists, please contact our technical support team through the Contact Support form, providing as much detail as possible about the issue.',
        'category': 'technical',
        'order': 1
    },
    {
        'question': 'How can I change my password?',
        'answer': 'To change your password, go to your profile settings and select "Change Password." You\'ll need to enter your current password and then create a new one. For security, choose a strong password with a mix of letters, numbers, and special characters.',
        'category': 'account',
        'order': 1
    },
    {
        'question': 'Can I use the platform on my mobile device?',
        'answer': 'Yes, our platform is fully responsive and works on all mobile devices. You can also download our mobile app for iOS and Android for an optimized experience.',
        'category': 'technical',
        'order': 2
    },
    {
        'question': 'How do I cancel an appointment?',
        'answer': 'To cancel an appointment, go to the Appointments section of your dashboard, find the appointment you wish to cancel, and click the "Cancel" button. Please note that cancellations within 24 hours of the appointment may incur a fee.',
        'category': 'appointments',
        'order': 2
    },
    {
        'question': 'What payment methods are accepted?',
        'answer': 'We accept all major credit cards (Visa, MasterCard, American Express, Discover), PayPal, and bank transfers. Payment information is securely stored and processed.',
        'category': 'billing',
        'order': 2
    },
    {
        'question': 'How is my data protected?',
        'answer': 'We take data security seriously. All data is encrypted both in transit and at rest using industry-standard encryption. We comply with HIPAA regulations and employ strict access controls. You can review our full privacy policy for more details.',
        'category': 'privacy',
        'order': 1
    },
    {
        'question': 'Can I delete my account?',
        'answer': 'Yes, you can delete your account by going to your profile settings and selecting "Delete Account." Please note that this action is permanent and will remove all your data from our system.',
        'category': 'account',
        'order': 2
    },
    {
        'question': 'How do I update my contact information?',
        'answer': 'You can update your contact information by going to your profile settings. Click on "Edit Profile" and update your email, phone number, address, or any other personal information.',
        'category': 'account',
        'order': 3
    },
    {
        'question': 'What happens if I miss an appointment?',
        'answer': 'If you miss an appointment without cancellation, it will be marked as a "No Show" in your record. Depending on your doctor\'s policy, you may be charged a missed appointment fee. We recommend rescheduling or canceling at least 24 hours in advance if you cannot attend.',
        'category': 'appointments',
        'order': 3
    },
    {
        'question': 'How do I set notification preferences?',
        'answer': 'To set notification preferences, go to your profile settings and select "Notifications." You can choose to receive notifications via email, SMS, or push notifications for different events such as appointment reminders, messages from your doctor, etc.',
        'category': 'technical',
        'order': 3
    },
    {
        'question': 'Can I get a receipt for my payments?',
        'answer': 'Yes, receipts are automatically generated for all payments. You can find them in the Billing section of your dashboard. You can also have receipts emailed to you by updating your notification preferences.',
        'category': 'billing',
        'order': 3
    }
]

# Create FAQ objects
for data in faq_data:
    FAQ.objects.get_or_create(
        question=data['question'],
        defaults={
            'answer': data['answer'],
            'category': data['category'],
            'order': data['order'],
            'is_published': True
        }
    )

print(f"Created {len(faq_data)} FAQs")
