"""Helmets bounded context: the real-time state of each known helmet.

`HelmetState` is the aggregate root — one instance per helmet, holding
presence (`status`, `last_seen_at`) and the latest reading per sensor type.
Its two domain methods (`first_contact`, `apply_batch`) are pure functional
updates; `application.device_state_manager` is the thin persistence-aware
wrapper that calls them.
"""
