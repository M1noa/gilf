# Core Infrastructure (Priority 1 - Essential)
## Dependencies
- [x] switch to discord.py-self for enhanced self-bot capabilities

## Architecture
- [x] separate bot and web server into different processes with IPC communication
- [x] implement process manager for handling bot and web server lifecycle
- [x] create shared memory space for fast data exchange between processes

## Security & Data Management
- [x] implement secure token storage with encryption in the python scripts directory
- [x] create json manager for safe file operations and corruption prevention
- [x] implement session management and token validation
- [x] add error handling and logging system with debug mode toggle
- [x] implement console output viewer in settings

## Core Features
- [x] implement websocket reconnection with exponential backoff
- [x] create command handler with support for both prefix and slash commands via Discord personal apps
- [x] implement rate limiting and cooldown system to prevent Discord rate limits
- [x] add message queue for Discord events

## File Organization & Structure
- [x] reorganize codebase with proper folder structure:
  - commands/ (for command modules)
  - handlers/ (for event handlers)
  - utils/ (for utility functions)
  - models/ (for data models)
  - services/ (for service classes)
  - config/ (for configuration files)

## Items Requiring Testing
**Note: The following items are implemented but need comprehensive testing:**
- [ ] **TEST REQUIRED:** Token encryption/decryption with TokenManager
- [ ] **TEST REQUIRED:** JSON file operations and backup/restore functionality
- [ ] **TEST REQUIRED:** WebSocket reconnection under various failure scenarios
- [ ] **TEST REQUIRED:** Rate limiting effectiveness during high-frequency operations
- [ ] **TEST REQUIRED:** Command handler with various command types and permissions
- [ ] **TEST REQUIRED:** Session management and cleanup
- [ ] **TEST REQUIRED:** Bot process lifecycle management
- [ ] **TEST REQUIRED:** Discord client event handling and user data retrieval
- [ ] **TEST REQUIRED:** Message queue processing under load
- [ ] **TEST REQUIRED:** Error handling and logging across all components

# Testing & Development (Priority 2 - Important)
## Test Framework
- [ ] create comprehensive test suite for all features
- [ ] implement automated testing for core functionality
- [ ] add integration tests for bot and web server communication
- [ ] create mock Discord API responses for testing
- [ ] implement test coverage reporting

# Web Interface (Priority 3 - User Info Display)
## User Information
- [ ] display user's username and discriminator
- [ ] show user ID and display name
- [ ] implement badge display system
- [ ] show server count with Nitro limit indicator
- [ ] display friend count with Nitro limit status
- [ ] add Nitro subscription status and perks
- [ ] implement real-time updates for all stats

# Bot Features (Priority 4 - Enhancement)
## Core Bot Features
- [ ] implement custom command creation system
- [ ] add user permission management (self-only execution)
- [ ] create event listener system
- [ ] implement message formatting utilities
- [ ] add command management UI in website
- [ ] implement nitro sniping with high-priority message handling

## Module System
- [ ] create plugin/script architecture with custom system language
- [ ] implement module hot-reloading
- [ ] add module dependency management
- [ ] create module marketplace interface
- [ ] implement settings persistence for users, scripts, and modules

# Quality of Life (Priority 5 - Optional)
## System Integration
- [ ] add system tray integration
- [ ] implement desktop notifications
- [ ] create auto-start functionality
- [ ] add update checker with GitHub version comparison (https://github.com/M1noa/gilf)

## Data Management
- [ ] implement automated backups
- [ ] create data import/export system
- [ ] add user preferences sync
- [ ] implement crash recovery system

## Performance
- [ ] add memory usage optimization
- [ ] implement request caching
- [ ] create performance monitoring dashboard
- [ ] add network usage statistics

## Event Handlers
- [ ] implement handlers for various events:
  - on_message
  - on_ready
  - on_guild_join
  - on_guild_leave
  - other essential Discord events
## Nitro Sniper Features
- [ ] implement nitro sniper settings in modules menu
- [ ] add support for multiple user and bot tokens for nitro checking
- [ ] configure main token for nitro redemption
- [ ] implement smart token rotation system
- [ ] add performance optimization for fastest possible detection

## Notification System
- [ ] create unified notification manager for all modules
- [ ] implement clickable notifications with action support
  - Message jumping
  - Quick actions
  - Status updates
- [ ] add customizable notification settings per module
- [ ] implement notification history and management
- [ ] create notification center in UI
  

- [ ] nitro sniper history command to see the history of nitro sniper attempts
- [ ]