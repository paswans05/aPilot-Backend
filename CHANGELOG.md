# Changelog

All notable changes to the **aPilot-Backend** service will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-05-22

### Added
- **Machine Details Persistence**:
  - Expanded `User` SQLAlchemy model and Pydantic schemas (`UserCreate`, `UserOut`) to save machine details: `system_user`, `hostname`, `platform`, `os_release`, and `arch`.
  - Added support for `avatar` and `about` fields to the `User` model.
  - Updated the `/register` endpoint to map these parameters from request bodies.
- **Dynamic Startup Migrations**:
  - Added self-migration code inside the startup handler in `app/main.py` using SQLAlchemy `inspect`. It automatically verifies and adds columns (`avatar`, `about`, `system_user`, `hostname`, `platform`, `os_release`, `arch`) to the `users` table via `ALTER TABLE` if they are missing.
- **Messenger/Chat Database Engine**:
  - Introduced models for `Chat` metadata, many-to-many `ChatParticipant` relations, and message history `Message`.
  - Developed Pydantic schemas representing contacts, chat structures, and message items.
  - Implemented API endpoints for `/contacts`, `/chat-list`, `/messages`, and `/profile/me`.
  - Configured database seeding at startup to add default contacts/users to the MySQL database for demo purposes.
