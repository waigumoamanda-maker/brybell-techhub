// routes/api.php
use App\Http\Controllers\PaymentController;

Route::post('/payments/initiate', [PaymentController::class, 'initiatePayment']);
Route::post('/payments/mpesa/callback', [PaymentController::class, 'mpesaCallback']);
Route::get('/payments/{transactionId}', [PaymentController::class, 'getPayment']);
Route::post('/payments/verify', [PaymentController::class, 'verifyPayment']);
Route::post('/payments/refund', [PaymentController::class, 'refundPayment']);