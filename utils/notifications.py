from flask_mail import Message
from flask import current_app, render_template_string
from extensions import mail
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for handling various types of notifications"""
    
    @staticmethod
    def send_email(to_email, subject, template_name, **template_vars):
        """Send email notification"""
        try:
            # Get email templates
            templates = NotificationTemplates()
            
            if hasattr(templates, template_name):
                html_body = getattr(templates, template_name)(**template_vars)
                text_body = NotificationService._html_to_text(html_body)
            else:
                raise ValueError(f"Template '{template_name}' not found")
            
            msg = Message(
                subject=subject,
                recipients=[to_email],
                html=html_body,
                body=text_body
            )
            
            mail.send(msg)
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    @staticmethod
    def send_transaction_notification(user_email, transaction_data):
        """Send transaction notification email"""
        subject = f"Transaction Alert - {transaction_data.get('type', '').title()}"
        
        return NotificationService.send_email(
            to_email=user_email,
            subject=subject,
            template_name='transaction_notification',
            **transaction_data
        )
    
    @staticmethod
    def send_welcome_email(user_email, user_name, verification_link=None):
        """Send welcome email to new user"""
        subject = "Welcome to Mobile Banking"
        
        return NotificationService.send_email(
            to_email=user_email,
            subject=subject,
            template_name='welcome_email',
            user_name=user_name,
            verification_link=verification_link
        )
    
    @staticmethod
    def send_password_reset_email(user_email, user_name, reset_link):
        """Send password reset email"""
        subject = "Password Reset Request"
        
        return NotificationService.send_email(
            to_email=user_email,
            subject=subject,
            template_name='password_reset_email',
            user_name=user_name,
            reset_link=reset_link
        )
    
    @staticmethod
    def send_security_alert(user_email, user_name, alert_type, details):
        """Send security alert email"""
        subject = f"Security Alert - {alert_type}"
        
        return NotificationService.send_email(
            to_email=user_email,
            subject=subject,
            template_name='security_alert',
            user_name=user_name,
            alert_type=alert_type,
            details=details,
            timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        )
    
    @staticmethod
    def send_account_status_change(user_email, user_name, account_number, status, reason=None):
        """Send account status change notification"""
        subject = f"Account Status Changed - {status.title()}"
        
        return NotificationService.send_email(
            to_email=user_email,
            subject=subject,
            template_name='account_status_change',
            user_name=user_name,
            account_number=account_number,
            status=status,
            reason=reason,
            timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        )
    
    @staticmethod
    def _html_to_text(html_content):
        """Convert HTML to plain text for email body"""
        # Simple HTML to text conversion
        import re
        
        # Remove HTML tags
        text = re.sub('<.*?>', '', html_content)
        
        # Replace HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        
        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        return text.strip()

class NotificationTemplates:
    """Email templates for various notifications"""
    
    def transaction_notification(self, transaction_id, amount, currency, type, description, 
                               balance_after=None, timestamp=None, **kwargs):
        """Transaction notification email template"""
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                .container { max-width: 600px; margin: 0 auto; }
                .header { background-color: #2c3e50; color: white; padding: 20px; text-align: center; }
                .content { background-color: #f8f9fa; padding: 20px; }
                .transaction-details { background-color: white; padding: 15px; margin: 10px 0; border-radius: 5px; }
                .amount { font-size: 24px; font-weight: bold; color: #27ae60; }
                .debit { color: #e74c3c; }
                .footer { text-align: center; margin-top: 20px; color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Transaction Alert</h1>
                </div>
                <div class="content">
                    <h2>Transaction Completed</h2>
                    <div class="transaction-details">
                        <p><strong>Transaction ID:</strong> {{ transaction_id }}</p>
                        <p><strong>Type:</strong> {{ type|title }}</p>
                        <p><strong>Description:</strong> {{ description }}</p>
                        <p><strong>Amount:</strong> 
                            <span class="amount {% if type in ['withdrawal', 'transfer', 'payment'] %}debit{% endif %}">
                                {{ currency }} {{ "{:.2f}".format(amount) }}
                            </span>
                        </p>
                        {% if balance_after is not none %}
                        <p><strong>Account Balance:</strong> {{ currency }} {{ "{:.2f}".format(balance_after) }}</p>
                        {% endif %}
                        <p><strong>Date & Time:</strong> {{ timestamp or "Just now" }}</p>
                    </div>
                    <p>If you did not authorize this transaction, please contact us immediately.</p>
                </div>
                <div class="footer">
                    <p>This is an automated notification from Mobile Banking App</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(template, **locals())
    
    def welcome_email(self, user_name, verification_link=None, **kwargs):
        """Welcome email template"""
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                .container { max-width: 600px; margin: 0 auto; }
                .header { background-color: #3498db; color: white; padding: 20px; text-align: center; }
                .content { background-color: #f8f9fa; padding: 20px; }
                .button { 
                    display: inline-block; 
                    background-color: #27ae60; 
                    color: white; 
                    padding: 12px 24px; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    margin: 10px 0;
                }
                .footer { text-align: center; margin-top: 20px; color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to Mobile Banking!</h1>
                </div>
                <div class="content">
                    <h2>Hello {{ user_name }}!</h2>
                    <p>Thank you for joining Mobile Banking App. We're excited to have you as part of our community.</p>
                    
                    {% if verification_link %}
                    <p>To get started, please verify your email address by clicking the button below:</p>
                    <p style="text-align: center;">
                        <a href="{{ verification_link }}" class="button">Verify Email Address</a>
                    </p>
                    {% endif %}
                    
                    <h3>What you can do with your account:</h3>
                    <ul>
                        <li>View your account balances and transaction history</li>
                        <li>Transfer money between accounts</li>
                        <li>Make payments and deposits</li>
                        <li>Set up account alerts and notifications</li>
                        <li>Manage your profile and security settings</li>
                    </ul>
                    
                    <p>If you have any questions, feel free to contact our support team.</p>
                </div>
                <div class="footer">
                    <p>Welcome aboard!<br>The Mobile Banking Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(template, **locals())
    
    def password_reset_email(self, user_name, reset_link, **kwargs):
        """Password reset email template"""
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                .container { max-width: 600px; margin: 0 auto; }
                .header { background-color: #e74c3c; color: white; padding: 20px; text-align: center; }
                .content { background-color: #f8f9fa; padding: 20px; }
                .button { 
                    display: inline-block; 
                    background-color: #e74c3c; 
                    color: white; 
                    padding: 12px 24px; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    margin: 10px 0;
                }
                .warning { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 10px 0; }
                .footer { text-align: center; margin-top: 20px; color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Password Reset Request</h1>
                </div>
                <div class="content">
                    <h2>Hello {{ user_name }}!</h2>
                    <p>We received a request to reset your password for your Mobile Banking account.</p>
                    
                    <div class="warning">
                        <strong>Security Notice:</strong> If you did not request this password reset, please ignore this email and contact support immediately.
                    </div>
                    
                    <p>To reset your password, click the button below:</p>
                    <p style="text-align: center;">
                        <a href="{{ reset_link }}" class="button">Reset Password</a>
                    </p>
                    
                    <p>This link will expire in 30 minutes for security reasons.</p>
                    
                    <p>For your security:</p>
                    <ul>
                        <li>Never share your password with anyone</li>
                        <li>Use a strong, unique password</li>
                        <li>Enable two-factor authentication</li>
                    </ul>
                </div>
                <div class="footer">
                    <p>Mobile Banking Security Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(template, **locals())
    
    def security_alert(self, user_name, alert_type, details, timestamp, **kwargs):
        """Security alert email template"""
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                .container { max-width: 600px; margin: 0 auto; }
                .header { background-color: #e74c3c; color: white; padding: 20px; text-align: center; }
                .content { background-color: #f8f9fa; padding: 20px; }
                .alert-box { background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; border-radius: 5px; margin: 10px 0; }
                .details { background-color: white; padding: 15px; margin: 10px 0; border-radius: 5px; }
                .footer { text-align: center; margin-top: 20px; color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚨 Security Alert</h1>
                </div>
                <div class="content">
                    <h2>Hello {{ user_name }}!</h2>
                    
                    <div class="alert-box">
                        <strong>Alert Type:</strong> {{ alert_type|title }}<br>
                        <strong>Time:</strong> {{ timestamp }}
                    </div>
                    
                    <div class="details">
                        <h3>Details:</h3>
                        {% for key, value in details.items() %}
                        <p><strong>{{ key|replace('_', ' ')|title }}:</strong> {{ value }}</p>
                        {% endfor %}
                    </div>
                    
                    <h3>What should you do?</h3>
                    <ul>
                        <li>If this was you, no action is needed</li>
                        <li>If this was not you, please contact support immediately</li>
                        <li>Consider changing your password</li>
                        <li>Review your recent account activity</li>
                    </ul>
                    
                    <p><strong>Need Help?</strong> Contact our security team if you have concerns about this alert.</p>
                </div>
                <div class="footer">
                    <p>Mobile Banking Security Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(template, **locals())
    
    def account_status_change(self, user_name, account_number, status, reason, timestamp, **kwargs):
        """Account status change notification template"""
        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                .container { max-width: 600px; margin: 0 auto; }
                .header { background-color: #f39c12; color: white; padding: 20px; text-align: center; }
                .content { background-color: #f8f9fa; padding: 20px; }
                .status-box { background-color: white; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 5px solid #f39c12; }
                .footer { text-align: center; margin-top: 20px; color: #666; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Account Status Update</h1>
                </div>
                <div class="content">
                    <h2>Hello {{ user_name }}!</h2>
                    <p>Your account status has been updated.</p>
                    
                    <div class="status-box">
                        <p><strong>Account:</strong> ****{{ account_number[-4:] if account_number|length > 4 else account_number }}</p>
                        <p><strong>New Status:</strong> {{ status|title }}</p>
                        {% if reason %}
                        <p><strong>Reason:</strong> {{ reason }}</p>
                        {% endif %}
                        <p><strong>Effective Date:</strong> {{ timestamp }}</p>
                    </div>
                    
                    {% if status.lower() == 'frozen' %}
                    <h3>What does this mean?</h3>
                    <ul>
                        <li>Your account has been temporarily frozen</li>
                        <li>You cannot make transactions until the account is unfrozen</li>
                        <li>Contact support if you have questions</li>
                    </ul>
                    {% elif status.lower() == 'active' %}
                    <h3>What does this mean?</h3>
                    <ul>
                        <li>Your account is now active and ready to use</li>
                        <li>You can make transactions and access all features</li>
                        <li>Thank you for banking with us</li>
                    </ul>
                    {% endif %}
                    
                    <p>If you have questions about this change, please contact our support team.</p>
                </div>
                <div class="footer">
                    <p>Mobile Banking Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(template, **locals())

# Helper functions for push notifications (placeholder for future implementation)
def send_push_notification(user_id, title, body, data=None):
    """Send push notification to mobile device"""
    # This would integrate with Firebase Cloud Messaging or similar service
    # For now, just log the notification
    logger.info(f"Push notification for user {user_id}: {title} - {body}")
    return True

def send_sms_notification(phone_number, message):
    """Send SMS notification"""
    # This would integrate with Twilio or similar SMS service
    # For now, just log the SMS
    logger.info(f"SMS to {phone_number}: {message}")
    return True
