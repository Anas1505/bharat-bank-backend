# Mobile Banking API Documentation

## Base URL
```
http://localhost:5000
```

## Authentication
Most endpoints require JWT authentication. Include the token in the Authorization header:
```
Authorization: Bearer <your_jwt_token>
```

---

## Authentication Endpoints

### Register User
**POST** `/api/auth/register`

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "1234567890",
  "date_of_birth": "1990-01-01"
}
```

**Response:**
```json
{
  "success": true,
  "message": "User registered successfully",
  "data": {
    "user": { ... },
    "access_token": "eyJ..."
  }
}
```

### Login
**POST** `/api/auth/login`

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "user": { ... }
  }
}
```

### Refresh Token
**POST** `/api/auth/refresh`

**Headers:** `Authorization: Bearer <refresh_token>`

**Response:**
```json
{
  "access_token": "eyJ..."
}
```

### Logout
**POST** `/api/auth/logout`

**Headers:** `Authorization: Bearer <access_token>`

### Get Current User
**GET** `/api/auth/me`

**Headers:** `Authorization: Bearer <access_token>`

---

## Account Endpoints

### Get All Accounts
**GET** `/api/accounts/`

**Headers:** `Authorization: Bearer <access_token>`

**Response:**
```json
{
  "success": true,
  "data": {
    "accounts": [
      {
        "id": "...",
        "account_number": "1234567890",
        "account_type": "savings",
        "balance": 1000.00,
        "currency": "USD",
        "is_primary": true
      }
    ]
  }
}
```

### Get Account Details
**GET** `/api/accounts/<account_id>`

### Create Account
**POST** `/api/accounts/`

**Request Body:**
```json
{
  "account_type": "savings",
  "currency": "USD",
  "initial_deposit": 100.00
}
```

### Get Account Balance
**GET** `/api/accounts/<account_id>/balance`

### Freeze Account
**POST** `/api/accounts/<account_id>/freeze`

### Unfreeze Account
**POST** `/api/accounts/<account_id>/unfreeze`

---

## Transaction Endpoints

### Get Transaction History
**GET** `/api/transactions/`

**Query Parameters:**
- `account_id` (optional)
- `start_date` (optional)
- `end_date` (optional)
- `transaction_type` (optional): deposit, withdrawal, transfer, payment
- `limit` (default: 50, max: 100)
- `offset` (default: 0)

**Response:**
```json
{
  "success": true,
  "data": {
    "transactions": [...],
    "pagination": {
      "total": 100,
      "limit": 50,
      "offset": 0,
      "has_more": true
    }
  }
}
```

### Get Transaction Details
**GET** `/api/transactions/<transaction_id>`

### Create Deposit
**POST** `/api/transactions/deposit`

**Request Body:**
```json
{
  "to_account_id": "...",
  "amount": 100.00,
  "description": "Salary deposit",
  "category": "salary"
}
```

### Create Withdrawal
**POST** `/api/transactions/withdrawal`

**Requires:** Fresh JWT token

**Request Body:**
```json
{
  "from_account_id": "...",
  "amount": 50.00,
  "description": "ATM withdrawal",
  "category": "other"
}
```

### Create Transfer
**POST** `/api/transactions/transfer`

**Requires:** Fresh JWT token

**Request Body:**
```json
{
  "from_account_id": "...",
  "to_account_id": "...",
  "amount": 200.00,
  "description": "Transfer to savings"
}
```

### Create Payment
**POST** `/api/transactions/payment`

**Requires:** Fresh JWT token

**Request Body:**
```json
{
  "from_account_id": "...",
  "amount": 150.00,
  "recipient": {
    "name": "Utility Company",
    "account_number": "9876543210"
  },
  "description": "Electric bill",
  "category": "utilities",
  "payment_method": "ach"
}
```

### Reverse Transaction
**POST** `/api/transactions/<transaction_id>/reverse`

**Requires:** Fresh JWT token

### Get Transaction Summary
**GET** `/api/transactions/summary`

**Query Parameters:**
- `start_date` (optional)
- `end_date` (optional)

---

## User Profile Endpoints

### Get Profile
**GET** `/api/users/profile`

### Update Profile
**PUT** `/api/users/profile`

**Request Body:**
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "phone": "1234567890",
  "address": {
    "street": "123 Main St",
    "city": "New York",
    "state": "NY",
    "zip": "10001"
  }
}
```

### Change Password
**PUT** `/api/users/password`

**Requires:** Fresh JWT token

**Request Body:**
```json
{
  "current_password": "OldPassword123!",
  "new_password": "NewPassword123!",
  "confirm_password": "NewPassword123!"
}
```

### Get Security Settings
**GET** `/api/users/security-settings`

### Update Security Settings
**PUT** `/api/users/security-settings`

**Request Body:**
```json
{
  "two_factor_enabled": true,
  "email_notifications": true,
  "sms_notifications": false,
  "login_alerts": true,
  "transaction_alerts": true
}
```

### Get Activity Log
**GET** `/api/users/activity-log`

**Query Parameters:**
- `limit` (default: 20)
- `offset` (default: 0)

---

## Error Responses

All endpoints return standardized error responses:

```json
{
  "success": false,
  "message": "Error description",
  "errors": { ... }  // Optional validation errors
}
```

**Common HTTP Status Codes:**
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `429` - Rate Limit Exceeded
- `500` - Internal Server Error

---

## Rate Limiting

Default rate limits:
- Most endpoints: 100 requests per hour
- Deposit: 20 per hour
- Withdrawal: 15 per hour
- Transfer: 15 per hour
- Payment: 10 per hour
- Account deactivation: 1 per day
- Data export: 1 per day

---

## Testing

Use the health check endpoint to verify API status:
**GET** `/api/health`

Response:
```json
{
  "status": "OK",
  "message": "Mobile Banking API is running",
  "version": "1.0.0"
}
```
