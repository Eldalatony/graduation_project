# Smart Home Energy Monitoring and Management System (SHEMMS)

## Project Overview
SHEMMS is a software platform that connects to smart plugs installed between home appliances and wall outlets to collect real-time electrical power data. It delivers monitoring, analytics, and control features to users.

## System Architecture
This project consists of four main microservices:
* **Frontend:** Next.js web application
* **Backend:** Node.js / Express API
* **Analytics:** Python / Flask intelligence service
* **Simulator:** Python-based smart plug data simulator

## Local Development Setup
1. Clone the repository.
2. Copy the `.env.example` files to `.env` in each respective service folder.
3. Run `docker-compose up --build` to start the full stack.
