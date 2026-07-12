"""HTTP transport: thin FastAPI routers. Parse/validate input (Pydantic
models already defined in `domain`), call an `application` use-case,
serialize the result. No business logic lives here.
"""
