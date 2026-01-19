// app/Models/Payment.php
namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Payment extends Model
{
    protected $fillable = [
        'order_id',
        'transaction_id',
        'amount',
        'phone_number',
        'payment_method',
        'status',
        'mpesa_receipt_number',
        'request_data',
        'callback_data'
    ];
    
    protected $casts = [
        'request_data' => 'array',
        'callback_data' => 'array',
        'amount' => 'decimal:2'
    ];
}

