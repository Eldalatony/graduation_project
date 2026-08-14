CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR NOT NULL,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    role VARCHAR NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    tariff_rate DECIMAL,
    reset_otp_hash VARCHAR,
    reset_otp_expires TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE appliances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR NOT NULL,
    node_key VARCHAR NOT NULL,
    gateway_id VARCHAR NOT NULL,
    is_active BOOLEAN DEFAULT false,
    room VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE spaces (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, name)
);

CREATE TABLE schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    appliance_id UUID REFERENCES appliances(id) ON DELETE CASCADE,
    action VARCHAR NOT NULL CHECK (action IN ('on', 'off')),
    cron_expression VARCHAR,
    timer_minutes INT,
    is_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    appliance_id UUID REFERENCES appliances(id) ON DELETE CASCADE,
    type VARCHAR NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT false,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
