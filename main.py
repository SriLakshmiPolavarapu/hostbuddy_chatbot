from flask import Flask, render_template, request, redirect, url_for
from flask_cors import CORS
import os
from groq import Groq
import paypalrestsdk

app = Flask(__name__)
CORS(app)

# Groq API Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# PayPal Configuration
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")

if PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET:
    paypalrestsdk.configure({
        "mode": PAYPAL_MODE,
        "client_id": PAYPAL_CLIENT_ID,
        "client_secret": PAYPAL_CLIENT_SECRET
    })

def get_replit_domain():
    """Get the Replit domain for PayPal redirect URLs"""
    replit_slug = os.getenv("REPL_SLUG", "app")
    replit_owner = os.getenv("REPL_OWNER", "user")
    return f"https://{replit_slug}.{replit_owner}.repl.co"

@app.route('/')
def home():
    """Home page with AI chat and PayPal payment options"""
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    """Handle AI chat requests using Groq API"""
    if not groq_client:
        return render_template('chat_response.html', 
                             prompt="Error",
                             response="GROQ_API_KEY is not configured. Please add it in the Secrets tab.",
                             model="Error")
    
    prompt = request.form.get('prompt', '')
    model = request.form.get('model', 'llama-3.3-70b-versatile')
    
    try:
        
        if not prompt:
            return render_template('chat_response.html',
                                 prompt="Error",
                                 response="Please provide a question or prompt.",
                                 model=model)
        
        # Call Groq API
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model=model,
            temperature=0.7,
            max_tokens=1024
        )
        
        ai_response = chat_completion.choices[0].message.content
        
        return render_template('chat_response.html',
                             prompt=prompt,
                             response=ai_response,
                             model=model)
    
    except Exception as e:
        return render_template('chat_response.html',
                             prompt=prompt,
                             response=f"Error calling Groq API: {str(e)}",
                             model=model)

@app.route('/create-payment', methods=['POST'])
def create_payment():
    """Create a PayPal payment"""
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        return """
        <html>
        <head><title>PayPal Not Configured</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>⚠️ PayPal Not Configured</h1>
            <p>Please add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to your Secrets.</p>
            <p>Get these from: <a href="https://developer.paypal.com/dashboard/">PayPal Developer Dashboard</a></p>
            <br><a href="/" style="color: #0070ba;">← Go Back</a>
        </body>
        </html>
        """
    
    try:
        amount = request.form.get('amount', '9.99')
        plan = request.form.get('plan', 'Basic')
        
        base_url = get_replit_domain()
        
        payment = paypalrestsdk.Payment({
            "intent": "sale",
            "payer": {
                "payment_method": "paypal"
            },
            "redirect_urls": {
                "return_url": f"{base_url}/payment-success",
                "cancel_url": f"{base_url}/payment-cancel"
            },
            "transactions": [{
                "item_list": {
                    "items": [{
                        "name": f"{plan} Plan",
                        "sku": plan.lower(),
                        "price": amount,
                        "currency": "USD",
                        "quantity": 1
                    }]
                },
                "amount": {
                    "total": amount,
                    "currency": "USD"
                },
                "description": f"Payment for {plan} plan"
            }]
        })
        
        if payment.create():
            for link in payment.links:
                if link.rel == "approval_url":
                    return redirect(link.href)
        else:
            return f"<h1>Error creating payment</h1><p>{payment.error}</p><a href='/'>Go back</a>"
    
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p><a href='/'>Go back</a>"

@app.route('/payment-success')
def payment_success():
    """Handle successful PayPal payment"""
    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')
    
    if payment_id and payer_id:
        try:
            payment = paypalrestsdk.Payment.find(payment_id)
            
            if payment.execute({"payer_id": payer_id}):
                return render_template('payment_success.html')
            else:
                return f"<h1>Payment execution failed</h1><p>{payment.error}</p>"
        except Exception as e:
            return f"<h1>Error</h1><p>{str(e)}</p>"
    
    return render_template('payment_success.html')

@app.route('/payment-cancel')
def payment_cancel():
    """Handle cancelled PayPal payment"""
    return render_template('payment_cancel.html')

@app.route('/api/health')
def health_check():
    """API health check endpoint"""
    return {
        'status': 'healthy',
        'groq_configured': GROQ_API_KEY is not None,
        'paypal_configured': PAYPAL_CLIENT_ID is not None and PAYPAL_CLIENT_SECRET is not None
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
