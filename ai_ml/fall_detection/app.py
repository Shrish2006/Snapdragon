from fastapi import FastAPI

app = FastAPI(title="SafeGuard Fall Detection")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
