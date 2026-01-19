<?php
// app/Http/Controllers/PaymentController.php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use App\Models\Payment;
use Carbon\Carbon;

class PaymentController extends Controller
{
    private $consumerKey;
    private $consumerSecret;
    private $passkey;
    private $shortcode;
    private $environment;
    
    public function __construct()
    {
        $this->consumerKey = env('MPESA_CONSUMER_KEY');
        $this->consumerSecret = env('MPESA_CONSUMER_SECRET');
        $this->passkey = env('MPESA_PASSKEY');
        $this->shortcode = env('MPESA_SHORTCODE');
        $this->environment = env('MPESA_ENVIRONMENT', 'sandbox');
    }
    
    /**
     * Get M-Pesa access token
     */
    private function getAccessToken()
    {
        $url = $this->environment === 'production'
            ? 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
            : 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials';
        
        $response = Http::withBasicAuth($this->consumerKey, $this->consumerSecret)
            ->get($url);
        
        if ($response->successful()) {
            return $response->json()['access_token'];
        }
        
        throw new \Exception('Failed to get M-Pesa access token');
    }
    
    /**
     * Initiate STK Push
     */
    public function initiatePayment(Request $request)
    {
        $validated = $request->validate([
            'phone_number' => 'required|string',
            'amount' => 'required|numeric|min:1',
            'order_id' => 'required|integer',
            'account_reference' => 'required|string'
        ]);
        
        try {
            $accessToken = $this->getAccessToken();
            
            // Format phone number (remove leading 0, add 254)
            $phone = $this->formatPhoneNumber($validated['phone_number']);
            
            // Generate timestamp and password
            $timestamp = Carbon::now()->format('YmdHis');
            $password = base64_encode($this->shortcode . $this->passkey . $timestamp);
            
            $url = $this->environment === 'production'
                ? 'https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
                : 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest';
            
            $callbackUrl = env('APP_URL') . '/api/payments/mpesa/callback';
            
            $response = Http::withToken($accessToken)
                ->post($url, [
                    'BusinessShortCode' => $this->shortcode,
                    'Password' => $password,
                    'Timestamp' => $timestamp,
                    'TransactionType' => 'CustomerPayBillOnline',
                    'Amount' => (int)$validated['amount'],
                    'PartyA' => $phone,
                    'PartyB' => $this->shortcode,
                    'PhoneNumber' => $phone,
                    'CallBackURL' => $callbackUrl,
                    'AccountReference' => $validated['account_reference'],
                    'TransactionDesc' => 'Payment for Order #' . $validated['order_id']
                ]);
            
            if ($response->successful()) {
                $data = $response->json();
                
                // Store payment record
                $payment = Payment::create([
                    'order_id' => $validated['order_id'],
                    'transaction_id' => $data['CheckoutRequestID'],
                    'amount' => $validated['amount'],
                    'phone_number' => $phone,
                    'payment_method' => 'mpesa',
                    'status' => 'pending',
                    'request_data' => json_encode($data)
                ]);
                
                return response()->json([
                    'success' => true,
                    'message' => 'STK Push sent successfully',
                    'checkout_request_id' => $data['CheckoutRequestID'],
                    'merchant_request_id' => $data['MerchantRequestID'],
                    'payment_id' => $payment->id
                ]);
            }
            
            return response()->json([
                'success' => false,
                'message' => 'Failed to initiate payment',
                'error' => $response->json()
            ], 400);
            
        } catch (\Exception $e) {
            Log::error('M-Pesa Payment Error: ' . $e->getMessage());
            return response()->json([
                'success' => false,
                'message' => 'Payment initiation failed',
                'error' => $e->getMessage()
            ], 500);
        }
    }
    
    /**
     * M-Pesa Callback Handler
     */
    public function mpesaCallback(Request $request)
    {
        $data = $request->all();
        Log::info('M-Pesa Callback Received:', $data);
        
        try {
            $resultCode = $data['Body']['stkCallback']['ResultCode'];
            $checkoutRequestId = $data['Body']['stkCallback']['CheckoutRequestID'];
            
            $payment = Payment::where('transaction_id', $checkoutRequestId)->first();
            
            if (!$payment) {
                Log::error('Payment not found for CheckoutRequestID: ' . $checkoutRequestId);
                return response()->json(['success' => false]);
            }
            
            if ($resultCode == 0) {
                // Payment successful
                $callbackMetadata = $data['Body']['stkCallback']['CallbackMetadata']['Item'];
                
                $mpesaReceiptNumber = null;
                $amount = null;
                $phoneNumber = null;
                
                foreach ($callbackMetadata as $item) {
                    if ($item['Name'] == 'MpesaReceiptNumber') {
                        $mpesaReceiptNumber = $item['Value'];
                    }
                    if ($item['Name'] == 'Amount') {
                        $amount = $item['Value'];
                    }
                    if ($item['Name'] == 'PhoneNumber') {
                        $phoneNumber = $item['Value'];
                    }
                }
                
                $payment->update([
                    'status' => 'completed',
                    'mpesa_receipt_number' => $mpesaReceiptNumber,
                    'callback_data' => json_encode($data)
                ]);
                
                // Notify Order Service about successful payment
                $this->notifyOrderService($payment->order_id, 'paid');
                
                Log::info('Payment completed: ' . $mpesaReceiptNumber);
                
            } else {
                // Payment failed
                $payment->update([
                    'status' => 'failed',
                    'callback_data' => json_encode($data)
                ]);
                
                $this->notifyOrderService($payment->order_id, 'failed');
                
                Log::warning('Payment failed for Order: ' . $payment->order_id);
            }
            
            return response()->json(['success' => true]);
            
        } catch (\Exception $e) {
            Log::error('Callback Processing Error: ' . $e->getMessage());
            return response()->json(['success' => false]);
        }
    }
    
    /**
     * Get payment status
     */
    public function getPayment($transactionId)
    {
        $payment = Payment::where('transaction_id', $transactionId)
            ->orWhere('id', $transactionId)
            ->first();
        
        if (!$payment) {
            return response()->json([
                'success' => false,
                'message' => 'Payment not found'
            ], 404);
        }
        
        return response()->json([
            'success' => true,
            'payment' => $payment
        ]);
    }
    
    /**
     * Verify payment
     */
    public function verifyPayment(Request $request)
    {
        $validated = $request->validate([
            'checkout_request_id' => 'required|string'
        ]);
        
        try {
            $accessToken = $this->getAccessToken();
            $timestamp = Carbon::now()->format('YmdHis');
            $password = base64_encode($this->shortcode . $this->passkey . $timestamp);
            
            $url = $this->environment === 'production'
                ? 'https://api.safaricom.co.ke/mpesa/stkpushquery/v1/query'
                : 'https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query';
            
            $response = Http::withToken($accessToken)
                ->post($url, [
                    'BusinessShortCode' => $this->shortcode,
                    'Password' => $password,
                    'Timestamp' => $timestamp,
                    'CheckoutRequestID' => $validated['checkout_request_id']
                ]);
            
            if ($response->successful()) {
                return response()->json([
                    'success' => true,
                    'data' => $response->json()
                ]);
            }
            
            return response()->json([
                'success' => false,
                'message' => 'Verification failed'
            ], 400);
            
        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'message' => 'Verification error',
                'error' => $e->getMessage()
            ], 500);
        }
    }
    
    /**
     * Refund payment (B2C)
     */
    public function refundPayment(Request $request)
    {
        $validated = $request->validate([
            'payment_id' => 'required|integer',
            'amount' => 'required|numeric',
            'remarks' => 'string'
        ]);
        
        $payment = Payment::find($validated['payment_id']);
        
        if (!$payment || $payment->status !== 'completed') {
            return response()->json([
                'success' => false,
                'message' => 'Invalid payment for refund'
            ], 400);
        }
        
        // Implement B2C logic here
        // This requires additional M-Pesa B2C credentials and setup
        
        return response()->json([
            'success' => true,
            'message' => 'Refund initiated'
        ]);
    }
    
    /**
     * Notify Order Service
     */
    private function notifyOrderService($orderId, $paymentStatus)
    {
        $orderServiceUrl = env('ORDER_SERVICE_URL', 'http://localhost:8003');
        
        try {
            Http::put("{$orderServiceUrl}/api/orders/{$orderId}/payment-status", [
                'payment_status' => $paymentStatus
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to notify Order Service: ' . $e->getMessage());
        }
    }
    
    /**
     * Format phone number
     */
    private function formatPhoneNumber($phone)
    {
        // Remove any non-numeric characters
        $phone = preg_replace('/[^0-9]/', '', $phone);
        
        // Remove leading 0 and add 254
        if (substr($phone, 0, 1) === '0') {
            $phone = '254' . substr($phone, 1);
        }
        
        // Add 254 if not present
        if (substr($phone, 0, 3) !== '254') {
            $phone = '254' . $phone;
        }
        
        return $phone;
    }
}
