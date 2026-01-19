// api-gateway/server.js
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const { createProxyMiddleware } = require('http-proxy-middleware');
const jwt = require('jsonwebtoken');

const app = express();
const PORT = process.env.PORT || 8000;
const SECRET_KEY = process.env.SECRET_KEY || 'your-secret-key-change-in-production';

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());

// Rate limiting
const limiter = rateLimit({
    windowMs: 1 * 60 * 1000, // 1 minute
    max: 100, // 100 requests per minute
    message: 'Too many requests from this IP, please try again later.'
});

app.use(limiter);

// Request logging
app.use((req, res, next) => {
    console.log(`${new Date().toISOString()} - ${req.method} ${req.path}`);
    next();
});

// JWT Verification Middleware
function verifyToken(req, res, next) {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];
    
    if (!token) {
        return res.status(401).json({ error: 'No token provided' });
    }
    
    try {
        const decoded = jwt.verify(token, SECRET_KEY);
        req.user = decoded;
        next();
    } catch (error) {
        return res.status(401).json({ error: 'Invalid token' });
    }
}

// Admin Authorization Middleware
function requireAdmin(req, res, next) {
    if (req.user && req.user.role === 'admin') {
        next();
    } else {
        res.status(403).json({ error: 'Admin access required' });
    }
}

// Service Configuration
const services = {
    product: 'http://localhost:8001',
    user: 'http://localhost:8002',
    order: 'http://localhost:8003',
    payment: 'http://localhost:8004',
    search: 'http://localhost:8005'
};

// Proxy Options
const createProxy = (target) => createProxyMiddleware({
    target,
    changeOrigin: true,
    pathRewrite: (path, req) => {
        return path.replace(/^\/api/, '/api');
    },
    onProxyReq: (proxyReq, req, res) => {
        // Forward user info if available
        if (req.user) {
            proxyReq.setHeader('X-User-Id', req.user.user_id);
            proxyReq.setHeader('X-User-Role', req.user.role);
        }
    },
    onError: (err, req, res) => {
        console.error('Proxy Error:', err);
        res.status(500).json({ error: 'Service unavailable' });
    }
});

// Health Check
app.get('/health', (req, res) => {
    res.json({ 
        status: 'healthy',
        timestamp: new Date().toISOString(),
        services: services
    });
});

// Routes

// Product Service (Public)
app.use('/api/products', createProxy(services.product));

// Search Service (Public)
app.use('/api/search', createProxy(services.search));

// User Service
app.use('/api/users/register', createProxy(services.user));
app.use('/api/users/login', createProxy(services.user));
app.use('/api/users/refresh', createProxy(services.user));
app.use('/api/users/reset-password', createProxy(services.user));

// Protected User Routes
app.use('/api/users/profile', verifyToken, createProxy(services.user));
app.use('/api/users/logout', verifyToken, createProxy(services.user));

// Order Service (Protected)
app.use('/api/orders', verifyToken, createProxy(services.order));

// Payment Service (Protected)
app.use('/api/payments/initiate', verifyToken, createProxy(services.payment));
app.use('/api/payments/verify', verifyToken, createProxy(services.payment));
app.use('/api/payments/refund', verifyToken, requireAdmin, createProxy(services.payment));

// Payment Callback (Public - M-Pesa calls this)
app.use('/api/payments/mpesa/callback', createProxy(services.payment));
app.use('/api/payments/:id', createProxy(services.payment));

// Admin Routes
app.use('/api/admin', verifyToken, requireAdmin, (req, res, next) => {
    // Route to appropriate service based on path
    const path = req.path;
    
    if (path.startsWith('/products')) {
        return createProxy(services.product)(req, res, next);
    } else if (path.startsWith('/orders')) {
        return createProxy(services.order)(req, res, next);
    } else if (path.startsWith('/users')) {
        return createProxy(services.user)(req, res, next);
    } else {
        res.status(404).json({ error: 'Admin route not found' });
    }
});

// Error handling middleware
app.use((err, req, res, next) => {
    console.error('Error:', err);
    res.status(err.status || 500).json({
        error: err.message || 'Internal server error',
        timestamp: new Date().toISOString()
    });
});

// 404 handler
app.use((req, res) => {
    res.status(404).json({ error: 'Route not found' });
});

// Start server
app.listen(PORT, () => {
    console.log(`API Gateway running on port ${PORT}`);
    console.log('Service Routes:');
    console.log(`  Product Service: ${services.product}`);
    console.log(`  User Service: ${services.user}`);
    console.log(`  Order Service: ${services.order}`);
    console.log(`  Payment Service: ${services.payment}`);
    console.log(`  Search Service: ${services.search}`);
});

// package.json for API Gateway
/*
{
  "name": "brybell-api-gateway",
  "version": "1.0.0",
  "description": "API Gateway for Brybell TechHub",
  "main": "server.js",
  "scripts": {
    "start": "node server.js",
    "dev": "nodemon server.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "cors": "^2.8.5",
    "helmet": "^7.0.0",
    "express-rate-limit": "^6.8.0",
    "http-proxy-middleware": "^2.0.6",
    "jsonwebtoken": "^9.0.1",
    "dotenv": "^16.3.1"
  },
  "devDependencies": {
    "nodemon": "^3.0.1"
  }
}
*/