# Bharat Bank Backend

A secure backend API for the **Bharat Bank Mobile Banking Application**, built using Python and Flask. The application provides RESTful APIs for user authentication, account management, banking transactions, notifications, and security-related features.

## Features

- User registration and login
- Secure password authentication
- JWT-based authentication
- Account and balance management
- Money transfers between accounts
- Deposit and withdrawal functionality
- Transaction history
- Transaction PIN support
- User profile management
- Notifications
- API rate limiting and security features

## Technologies Used

- **Python**
- **Flask**
- **MongoDB**
- **JWT Authentication**
- **Flask-CORS**
- **Flask-Limiter**
- **Password Hashing**

## Project Structure

```text
bharat-bank-backend/
│
├── models/          # Database models
├── routes/          # API routes and endpoints
├── utils/           # Utility functions
├── python-backend/  # Backend-related modules
│
├── app.py           # Main application entry point
├── config.py        # Application configuration
├── diagnose.py      # Diagnostic utilities
├── .env.example     # Environment variable template
└── Procfile         # Deployment configuration
```

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Anas1505/bharat-bank-backend.git
cd bharat-bank-backend
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate the virtual environment.

**Windows:**

```bash
venv\Scripts\activate
```

**macOS/Linux:**

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file based on `.env.example` and add the required configuration values.

> Never upload your `.env` file or sensitive credentials to GitHub.

### 5. Run the application

```bash
python app.py
```

The API will start locally and can be accessed through the configured server address.

## API Modules

The backend includes APIs for:

- Authentication
- User management
- Bank accounts
- Transactions
- Notifications

## Security

The application includes security measures such as password hashing, JWT-based authentication, API rate limiting, and environment-based configuration to help protect sensitive application data.

## Project Purpose

This project was developed as part of a **Mobile Banking Application** project to demonstrate backend development, RESTful API design, database integration, and security practices in a banking application.

## Author

**Anas Khamkar**
